"""Reasoning-budget A/B on the champion (Barry, 2026-09-15: "now do the speed
stuff, the reasoning budget thing").

The fork's --reasoning-budget is SERVER-WIDE (measured 2026-09-08: per-request
overrides are ignored), so each budget means a server restart. Same hard set
(H1-H5, the puzzles both models aced) + two real office-prompt items (R1
judgment, R4 cannabis-legal) per budget, timed. Correctness AND seconds are
printed side by side; the call is Barry's.

Usage: venv/Scripts/python.exe scripts/bench_reasoning_budget_2026_09_15.py [budgets...]
Default budgets: 3072 2048 1536. Holds the render flag; releases it.
"""
import asyncio
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "backend"))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import bonsai_llm      # noqa: E402
import llm_router      # noqa: E402
import bench_three_models as bench  # noqa: E402
# HARD set + run_hard copied from bench_qwen38_on_prism_2026_09_15.py (that
# module asserts a challenger model path on import, so it cannot be imported here).
import re  # noqa: E402


def _num(r, want):
    return re.search(rf"(?<![\d.]){re.escape(want)}(?![\d.])", r) is not None


HARD = [
    ("H1 margin + discount + shipping",
     "A bottle sells for $60 at a 40% gross margin. A customer uses a 15% off "
     "code. The store pays $9 to ship the order and the customer pays no "
     "shipping. What is the store's gross profit in dollars on that one bottle "
     "after shipping? Answer with just the number.",
     lambda r: _num(r, "6")),                       # cost 36, price 51, 51-36-9
    ("H2 liar puzzle (exactly one true)",
     "Five bottles A, B, C, D, E; exactly one is counterfeit. A says: 'B is "
     "counterfeit.' B says: 'D is counterfeit.' C says: 'I am not counterfeit.' "
     "D says: 'B is lying.' Exactly ONE of these four statements is true. Which "
     "bottle is counterfeit? Answer with just the letter.",
     lambda r: re.sub(r"[^A-Z]", "", r.strip().upper()[:3]) .startswith("C")),
    ("H3 GPU scheduling",
     "Three renders on one GPU, one at a time, no pausing: A takes 9 minutes, "
     "B takes 4, C takes 6. B may only start after A has finished. C may not "
     "start before minute 5. Starting at minute 0, what is the earliest minute "
     "at which all three are finished? Answer with just the number.",
     lambda r: _num(r, "19")),
    ("H4 rate trap",
     "Last month a discount code was used on 3 of 60 orders. This month it was "
     "used on 3 of 15 orders. Did the usage RATE go up, go down, or stay the "
     "same? Answer with one word: up, down, or same.",
     lambda r: "up" in r.lower()[:40] and "down" not in r.lower()[:40]),
    ("H5 substantiation trap (legal)",
     "One customer says our fertilizer raised his yield 40%. Can we run an ad "
     "that says '40% yield increase'? Answer YES or NO as the first word, then "
     "one sentence.",
     lambda r: r.strip().upper().startswith("NO")),
]


async def run_hard(label: str) -> list:
    out = []
    print(f"\n--- HARD set: {label} ---")
    for name, q, grader in HARD:
        try:
            reply, secs, _ = await bench.ask(bench.BONSAI, bench.MINIMAL_SYS, q, use_tools=False)
            ok = bool(grader(reply))
            out.append({"test": name, "pass": ok, "secs": round(secs, 1), "reply": reply[:400]})
            print(f"  {name}: {'PASS' if ok else 'FAIL'} ({secs:.1f}s)  -> {reply[:80]!r}")
        except Exception as exc:  # noqa: BLE001
            out.append({"test": name, "pass": False, "error": str(exc)[:200]})
            print(f"  {name}: ERROR {exc}")
    return out




BUDGETS = [int(a) for a in sys.argv[1:]] or [3072, 2048, 1536]
FLAG = os.path.join(REPO, "data", "video_rendering.flag")
TOKEN = f"bench-budget-{os.getpid()}"
REAL = [x for x in bench.REAL if x[0].startswith(("R1", "R4"))]


async def run_budget(budget: int, cio_prompt: str) -> dict:
    await bonsai_llm.stop_server()
    await llm_router.unload_all_models()
    bonsai_llm.REASONING_BUDGET = budget
    if not await bonsai_llm.ensure_running():
        return {"budget": budget, "error": "server did not start"}
    res = {"budget": budget, "hard": await run_hard(f"budget {budget}"), "real": []}
    for name, q, _g in REAL:
        t0 = time.monotonic()
        reply, secs, log = await bench.ask(bench.BONSAI, cio_prompt, q, use_tools=True)
        res["real"].append({"test": name, "secs": round(secs, 1), "chars": len(reply),
                            "tools": log, "refused": bench.looks_refused(reply), "reply": reply[:1500]})
        print(f"  {name}: {secs:.1f}s, {len(reply)} chars, tools={log or 'none'}"
              + (" <-- REFUSED" if bench.looks_refused(reply) else ""))
    return res


async def main():
    with open(FLAG, "w", encoding="utf-8") as fh:
        fh.write(TOKEN)
    try:
        cio_prompt = bench.build_cio_prompt()
        out = []
        for b in BUDGETS:
            print(f"\n===== reasoning budget {b} =====")
            out.append(await run_budget(b, cio_prompt))
        await bonsai_llm.stop_server()
        path = os.path.join(REPO, "data", "bench_reasoning_budget_2026-09-15.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, ensure_ascii=False)
        print("\n================ SCOREBOARD ================")
        print(f"{'budget':>7} | {'hard':>5} | {'hard secs':>9} | {'R1 secs':>7} | {'R4 secs':>7} | R1 chars | R4 chars")
        for r in out:
            if "error" in r:
                print(f"{r['budget']:>7} | ERROR {r['error']}")
                continue
            hp = sum(1 for x in r["hard"] if x.get("pass"))
            hs = round(sum(x.get("secs", 0) for x in r["hard"]), 1)
            rs = {x["test"][:2]: x for x in r["real"]}
            print(f"{r['budget']:>7} | {hp:>3}/5 | {hs:>9} | {rs.get('R1',{}).get('secs','-'):>7} | "
                  f"{rs.get('R4',{}).get('secs','-'):>7} | {rs.get('R1',{}).get('chars','-'):>8} | {rs.get('R4',{}).get('chars','-'):>8}")
        print(f"\nsaved -> {path}")
    finally:
        try:
            with open(FLAG, encoding="utf-8") as fh:
                mine = fh.read().strip() == TOKEN
            if mine:
                os.remove(FLAG)
        except OSError:
            pass
        print("flag released:", not os.path.exists(FLAG))


if __name__ == "__main__":
    asyncio.run(main())
