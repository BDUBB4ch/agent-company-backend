"""Qwen3.8-27B abliterated (q3_K) through the PRISM VULKAN llama-server.

Ollama 0.32.4 refuses it ('unknown renderer "qwen3.8"' -- a missing chat
template renderer, the qwen35 family itself loads). Same GGUF blob, same
server Bonsai runs on, --jinja uses the template baked into the file, so the
comparison against the champion is like-for-like on the same engine.
Context is 32K here: a 14GB q3_K plus the office's 98K KV does not fit 16GB.
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

# argv[1] = GGUF path, argv[2] = ctx. Defaults = the q3_K Ollama blob at 32K
# (run 1, 2026-09-15: 5/5 logic but 7 tok/s -- 13.1GB dedicated + 3.0GB
# spilled, disqualified on fit).
BLOB = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\Users\Owner\.ollama\models\blobs\sha256-a82fe31ff8716377d1dd2f47e1dc1847b96566ddcfa9a3c394a1b6ecf7adc75c"
CTX = sys.argv[2] if len(sys.argv) > 2 else "32768"
os.environ["BONSAI_MODEL_PATH"] = BLOB
os.environ["BONSAI_NUM_CTX"] = CTX

import bonsai_llm      # noqa: E402
import llm_router      # noqa: E402
import bench_three_models as bench  # noqa: E402

assert bonsai_llm.BONSAI_MODEL_PATH == BLOB, bonsai_llm.BONSAI_MODEL_PATH
assert bonsai_llm.BONSAI_NUM_CTX == int(CTX), bonsai_llm.BONSAI_NUM_CTX
OUT_TAG = os.path.splitext(os.path.basename(BLOB))[0][-24:].replace(".", "_")

FLAG = os.path.join(REPO, "data", "video_rendering.flag")
TOKEN = f"bench-qwen38-prism-{os.getpid()}"
CHAMPION = os.path.join(REPO, "models", "bonsai", "Ternary-Bonsai-27B-Abliterated-LowDeg-Q2_0.gguf")

# HARDER SET (Barry, 2026-09-15: "is the reasoning better and logic?") -- the
# five-item battery ceilings at 5/5 for both, so it cannot separate them.
# Each item has ONE defensible answer; graders are still keyword matchers.
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


async def main():
    with open(FLAG, "w", encoding="utf-8") as fh:
        fh.write(TOKEN)
    try:
        # The office's own Bonsai may be up on 8811 -- it must go, or the
        # bench would talk to the champion while believing it is the challenger.
        await bonsai_llm.stop_server()
        await llm_router.unload_all_models()
        print(f"challenger on Prism: {BLOB}\nctx {bonsai_llm.BONSAI_NUM_CTX}")
        cio_prompt = bench.build_cio_prompt()
        t0 = time.monotonic()
        res = await bench.run_contender(bench.BONSAI, cio_prompt)
        res["contender"] = f"Qwen3.8-27B abliterated {os.path.basename(BLOB)} on Prism/Vulkan (ctx {CTX})"
        res["hard"] = await run_hard("challenger")
        await bonsai_llm.stop_server()
        # Champion on the SAME hard set, same server, same session.
        bonsai_llm.BONSAI_MODEL_PATH = CHAMPION
        if await bonsai_llm.ensure_running():
            res["hard_champion"] = await run_hard("champion (Bonsai ternary)")
        else:
            res["hard_champion"] = [{"error": "champion server did not start"}]
        await bonsai_llm.stop_server()
        hc = [x for x in res["hard_champion"] if "pass" in x]
        hx = [x for x in res["hard"] if "pass" in x]
        print(f"\nHARD: challenger {sum(1 for x in hx if x['pass'])}/{len(HARD)}  |  "
              f"champion {sum(1 for x in hc if x['pass'])}/{len(HARD)}")
        out = os.path.join(REPO, "data", f"bench_qwen38_on_prism_{OUT_TAG}_2026-09-15.json")
        with open(out, "w", encoding="utf-8") as fh:
            json.dump([res], fh, indent=2, ensure_ascii=False)
        logic = [x for x in res["logic"] if "pass" in x]
        print(f"\nsaved -> {out}  ({(time.monotonic()-t0)/60:.1f} min)")
        print(f"logic {sum(1 for x in logic if x['pass'])}/{len(logic)} in "
              f"{round(sum(x.get('secs',0) for x in res['logic']),1)}s | refusals "
              f"{sum(1 for x in res['real'] if x.get('refused'))}/4 | tools "
              f"{sum(len(x.get('tools') or []) for x in res['real'])} | errors {res['errors']}")
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
