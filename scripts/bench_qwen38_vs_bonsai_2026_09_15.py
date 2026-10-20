"""THE GATE for Qwen3.8-27B abliterated (huihui, q3_K, 14GB) vs the champion.

Barry, 2026-09-15: "this first, then my agents." Same items and graders as
bench_three_models.py (L1-L5 logic, the AOV false-premise trap, read_skill,
the cannabis-legal refusal probe), BOTH contenders run back to back in one
session so the card's state is the same for each. Nothing swaps on the
strength of this file -- Barry reads the replies (graders are keyword
matchers, SPOT-CHECK them) and makes the call.

Usage:  venv/Scripts/python.exe scripts/bench_qwen38_vs_bonsai_2026_09_15.py
Output: data/bench_qwen38_vs_bonsai_2026-09-15.json (new file, history kept)
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

CHALLENGER = "huihui_ai/qwen3.8-abliterated:27b-q3_K"


def summarize(r: dict) -> dict:
    logic = [x for x in r["logic"] if "pass" in x]
    real_speeds = [x["cps"] for x in r["real"] if x.get("cps")]
    return {
        "contender": r["contender"],
        "logic": f"{sum(1 for x in logic if x['pass'])}/{len(logic)}",
        "logic_secs": round(sum(x.get("secs", 0) for x in r["logic"]), 1),
        "office_cps": round(sum(real_speeds) / len(real_speeds), 1) if real_speeds else 0,
        "aov_trap": next((x.get("pass") for x in r["real"] if x["test"].startswith("R2")), None),
        "refusals": sum(1 for x in r["real"] if x.get("refused")),
        "tool_calls": sum(len(x.get("tools") or []) for x in r["real"]),
        "gpu": r.get("gpu", ""),
        "errors": r.get("errors", []),
    }


FLAG = os.path.join(REPO, "data", "video_rendering.flag")
TOKEN = f"bench-qwen38-{os.getpid()}"


def _hold_card():
    """Own the GPU for the bench (the 2026-08-29 rule for standalone GPU
    scripts). Without it the backend's idle loops reload Bonsai the moment the
    bench evicts it -- measured on the first attempt: 11.2GB of Bonsai back on
    the card, the 14GB challenger stalled. With the flag up, llm_router.generate
    answers every office call with the bracketed 'render in progress' line."""
    with open(FLAG, "w", encoding="utf-8") as fh:
        fh.write(TOKEN)


def _release_card():
    try:
        with open(FLAG, encoding="utf-8") as fh:
            if fh.read().strip() == TOKEN:
                os.remove(FLAG)
    except OSError:
        pass


async def main():
    _hold_card()
    try:
        await _main()
    finally:
        _release_card()


async def _main():
    print(f"champion:   Bonsai  {os.path.basename(bonsai_llm.BONSAI_MODEL_PATH)}")
    print(f"challenger: {CHALLENGER}")
    cio_prompt = bench.build_cio_prompt()
    print(f"CIO office prompt: {len(cio_prompt)} chars (~{len(cio_prompt)//4} tokens)")

    results = []
    t0 = time.monotonic()
    for contender in (CHALLENGER, bench.BONSAI):
        res = await bench.run_contender(contender, cio_prompt)
        if contender == bench.BONSAI:
            res["contender"] = "Bonsai 27B ABLITERATED (ternary, champion)"
        results.append(res)
    await llm_router.unload_all_models()

    out = os.path.join(REPO, "data", "bench_qwen38_vs_bonsai_2026-09-15.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)
    print(f"\nsaved -> {out}   ({(time.monotonic()-t0)/60:.1f} min total)")

    print("\n================ SCOREBOARD ================")
    for r in results:
        s = summarize(r)
        print(f"\n{s['contender']}")
        print(f"  logic        {s['logic']}  in {s['logic_secs']}s")
        print(f"  office cps   {s['office_cps']}")
        print(f"  AOV trap     {'PASSED (asked, did not invent)' if s['aov_trap'] else 'FAILED (invented a number)'}")
        print(f"  refusals     {s['refusals']}/4")
        print(f"  tool calls   {s['tool_calls']} structured")
        if s["gpu"]:
            print(f"  GPU          {s['gpu']}")
        if s["errors"]:
            print(f"  ERRORS       {s['errors']}")


if __name__ == "__main__":
    asyncio.run(main())
