"""
Corrected tool-use leg of the three-way benchmark.

bench_three_models.py passed office_name=None, so read_skill had no agent
whose skill list to resolve against and failed for every contender -- the
"0 structured tool calls" and Bonsai's "I can't pull the skill" were harness
artifacts, not model behaviour. This re-runs ONLY that leg with the real
office_name, which is what /api/chat actually passes.

Everything else from that run (logic, speed, AOV trap, GPU residency) was
unaffected and is not repeated here.

SAFETY: no brain writes. One model on the GPU at a time. Web search excluded.
Bonsai's server always stopped in a finally.
"""
import asyncio
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

import agents          # noqa: E402
import bonsai_llm      # noqa: E402
import llm_router      # noqa: E402
import memory          # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CURRENT = "huihui_ai/qwen3.5-abliterated:9b"
Q8 = "huihui_ai/qwen3.5-abliterated:9b-q8_0"
BONSAI = "BONSAI"

AGENT_ID = "cio"
OFFICE = agents.AGENTS[AGENT_ID]["office_name"]

QUESTION = ("What are the highest-value email types for B Dubb Grows, and why "
            "those? Use your skills if you need them.")


def build_cio_prompt() -> str:
    a = agents.AGENTS[AGENT_ID]
    pins = agents.PINNED_SKILLS.get(AGENT_ID, [])
    return (
        f"{a['system_prompt']}\n\n{memory.pinned_skills_block(OFFICE, pins)}\n"
        f"--- BUSINESS KNOWLEDGE (the brain) ---\n"
        f"{memory.brain_context_block(OFFICE, include_shared=True, pinned_titles=pins)}\n"
        f"--- END BUSINESS KNOWLEDGE ---\n\n"
        f"Hard rule: you cannot post, send, email, or publish anything yourself."
    )


async def run(contender: str, sp: str) -> dict:
    label = "Bonsai 27B (ternary)" if contender == BONSAI else contender
    await llm_router.unload_all_models()
    log = []
    row = {"contender": label}
    try:
        if contender == BONSAI:
            if not await bonsai_llm.ensure_running():
                return {"contender": label, "error": "server did not start"}
            t0 = time.monotonic()
            reply = await bonsai_llm.call_bonsai(
                system_prompt=sp,
                messages=[{"role": "user", "content": QUESTION}],
                dispatch_tool_call=llm_router._dispatch_tool_call,
                tools_list=[llm_router.READ_SKILL_TOOL],
                tool_call_log=log,
                office_name=OFFICE,          # <-- the fix
            )
        else:
            t0 = time.monotonic()
            reply = await llm_router.call_ollama(
                system_prompt=sp,
                messages=[{"role": "user", "content": QUESTION}],
                model=contender,
                use_tools=True,
                allow_web_search=False,
                tool_call_log=log,
                office_name=OFFICE,          # <-- the fix
            )
        secs = time.monotonic() - t0
        row.update({"secs": round(secs, 1), "chars": len(reply), "tools": log,
                    "tool_failed": "can't pull" in reply.lower() or "couldn't pull" in reply.lower(),
                    "reply": reply[:700]})
    except Exception as exc:  # noqa: BLE001
        row["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if contender == BONSAI:
            await bonsai_llm.stop_server()
    print(f"  {label}: {row.get('secs')}s tools={row.get('tools')} "
          f"tool_failed={row.get('tool_failed')}")
    return row


async def main():
    sp = build_cio_prompt()
    print(f"CIO prompt {len(sp)} chars, office_name={OFFICE}\n")
    results = [await run(c, sp) for c in (CURRENT, Q8, BONSAI)]
    await llm_router.unload_all_models()

    out = os.path.join(REPO, "data", "bench_tools_fixed.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)
    print(f"\nsaved -> {out}")
    for r in results:
        print(f"\n=== {r['contender']} ===")
        if r.get("error"):
            print("  ERROR", r["error"]); continue
        print(f"  {r['secs']}s, {r['chars']} chars, structured tools: {r['tools'] or 'none'}")
        print("  " + (r["reply"][:300].replace("\n", "\n  ")))


if __name__ == "__main__":
    asyncio.run(main())
