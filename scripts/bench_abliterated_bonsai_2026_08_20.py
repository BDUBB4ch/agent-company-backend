"""Reasoning bench for the ABLITERATED Bonsai (2026-08-20).

Barry's ruling: "if this new abliterated Bonsai 27b works, then everybody should
get it." This is the gate. Reuses bench_three_models.py's exact items and graders
(L1-L5 logic + the real office-prompt suite incl. the AOV false-premise trap) so
the numbers are directly comparable to the parent's recorded run:
  data/bench_three_models.json (2026-08-11): parent logic 5/5, 43.3s over the
  5 items, 75.5 chars/s office work, structured read_skill, zero refusals.

Output goes to a NEW file -- the historical record is not overwritten.
Graders are keyword matchers; SPOT-CHECK replies before believing them.
"""
import asyncio
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "backend"))
sys.path.insert(0, os.path.join(REPO, "scripts"))

ABLITERATED = os.path.join(REPO, "models", "bonsai",
                           "Ternary-Bonsai-27B-Abliterated-LowDeg-Q2_0.gguf")
os.environ.setdefault("BONSAI_MODEL_PATH", ABLITERATED)

import bonsai_llm      # noqa: E402
import llm_router      # noqa: E402
import bench_three_models as bench  # noqa: E402

assert bonsai_llm.BONSAI_MODEL_PATH == ABLITERATED, (
    f"wrong model path loaded: {bonsai_llm.BONSAI_MODEL_PATH}")


async def main():
    print(f"model under test: {bonsai_llm.BONSAI_MODEL_PATH}")
    cio_prompt = bench.build_cio_prompt()
    print(f"CIO office prompt: {len(cio_prompt)} chars")

    res = await bench.run_contender(bench.BONSAI, cio_prompt)
    res["contender"] = "Bonsai 27B ABLITERATED (LowDeg Q2_0)"
    await llm_router.unload_all_models()

    out = os.path.join(REPO, "data", "bench_abliterated_bonsai_2026-08-20.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump([res], fh, indent=2, ensure_ascii=False)
    print(f"\nsaved -> {out}")

    logic = [x for x in res["logic"] if "pass" in x]
    passed = sum(1 for x in logic if x["pass"])
    total_secs = round(sum(x.get("secs", 0) for x in res["logic"]), 1)
    real_speeds = [x["cps"] for x in res["real"] if x.get("cps")]
    ravg = round(sum(real_speeds) / len(real_speeds), 1) if real_speeds else 0
    refusals = sum(1 for x in res["real"] if x.get("refused"))
    toolcalls = sum(len(x.get("tools") or []) for x in res["real"])
    trap = next((x.get("pass") for x in res["real"] if x["test"].startswith("R2")), None)

    print("\n===== ABLITERATED vs PARENT (recorded 2026-08-11) =====")
    print(f"  logic       {passed}/{len(logic)}   (parent: 5/5, 43.3s)   this run: {total_secs}s")
    print(f"  office cps  {ravg}   (parent: 75.5)")
    print(f"  AOV trap    {'PASSED' if trap else 'FAILED'}   (parent: PASSED)")
    print(f"  refusals    {refusals}   (parent: 0)")
    print(f"  tool calls  {toolcalls} structured   (parent: structured read_skill)")


if __name__ == "__main__":
    asyncio.run(main())
