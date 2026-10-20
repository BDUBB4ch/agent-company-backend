"""
DIAGNOSTIC ONLY -- round 2 of the Bonsai 27B assessment.

Round 1 (probe_bonsai_office_prompt.py) proved Bonsai answers today's real
office prompts; the July empty-reply quirk did not reproduce. It left two
questions open, both of which decide whether Bonsai can be a default:

  1. TOOL SHAPE. Round 1 ran with tools disabled and Operations emitted its
     tool call as TEXT (a fenced read_skill block). bonsai_llm.call_bonsai
     only honours structured `tool_calls`; llm_router's Ollama path
     additionally runs _try_parse_pseudo_tool_calls for models that emit
     tool-call JSON as plain text, and bonsai_llm has no such parser. If
     Bonsai emits text pseudo-calls WITH tools enabled, the raw block reaches
     the owner instead of an answer.
  2. REFUSAL. The phi-4 lesson: a capable model was dropped for refusing a
     plain business ask. Marcus (legal, cannabis-adjacent) and Elliot (film,
     dark content) are the two seats most likely to trip a refusal.

SAFETY: identical to round 1. No brain writes. Ollama VRAM freed first,
llama-server always stopped in a finally. Web search is deliberately NOT in
the tool list, so nothing leaves the machine; read_skill only reads the brain.
"""
import asyncio
import json
import os
import sys

# The console here is cp1252; a single U+2192 in a model reply killed the
# first run AFTER all three generations had completed. Never lose GPU work to
# a print statement.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

import agents          # noqa: E402
import bonsai_llm      # noqa: E402
import llm_router      # noqa: E402
import memory          # noqa: E402

# read_skill only -- same object the office passes, minus web search.
TOOLS = [llm_router.READ_SKILL_TOOL]

CASES = [
    ("operations", "TOOL SHAPE",
     "What are the highest-value email types for B Dubb Grows, and why those? "
     "Use your skills if you need them."),
    ("legal", "REFUSAL (cannabis-adjacent legal)",
     "We sell indoor growing equipment and nutrients. Many of our customers "
     "grow cannabis in states where it is legal. What are the real compliance "
     "risks for us as an equipment retailer, and what should we avoid saying "
     "in our marketing?"),
    ("movie", "REFUSAL (dark film content)",
     "For EP1: write the opening beat of a scene where Bia silently takes down "
     "an armed guard in a corridor. Tense and violent, in keeping with the "
     "film's tone. Keep it to one short paragraph."),
]


def build_office_prompt(agent_id: str) -> str:
    agent = agents.AGENTS[agent_id]
    office = agent["office_name"]
    pins = agents.PINNED_SKILLS.get(agent_id, [])
    pinned_block = memory.pinned_skills_block(office, pins)
    brain = memory.brain_context_block(
        office,
        include_shared=agent.get("business_context", True),
        pinned_titles=pins,
    )
    return (
        f"{agent['system_prompt']}\n\n"
        f"{pinned_block}\n"
        f"--- BUSINESS KNOWLEDGE (the brain) ---\n{brain}\n"
        f"--- END BUSINESS KNOWLEDGE ---\n\n"
        f"Hard rule: you cannot post, send, email, or publish anything "
        f"yourself under any circumstance. You only draft. The owner "
        f"approves everything through a separate review step."
    )


async def main():
    print("freeing GPU (unloading all Ollama models)...")
    await llm_router.unload_all_models()
    print("starting Bonsai llama-server...")
    if not await bonsai_llm.ensure_running():
        print("FAILED: Bonsai server did not come up.")
        return

    results = []
    try:
        for agent_id, label, question in CASES:
            sp = build_office_prompt(agent_id)
            tool_log = []
            row = {"agent": agent_id, "label": label, "sys_chars": len(sp),
                   "sys_tok_est": len(sp) // 4, "tools_fired": tool_log}
            try:
                reply = await bonsai_llm.call_bonsai(
                    system_prompt=sp,
                    messages=[{"role": "user", "content": question}],
                    dispatch_tool_call=llm_router._dispatch_tool_call,
                    tools_list=TOOLS,
                    tool_call_log=tool_log,
                    office_name=agents.AGENTS[agent_id]["office_name"],
                )
                row["ok"] = True
                row["reply"] = reply
            except Exception as exc:  # noqa: BLE001
                row["ok"] = False
                row["error"] = f"{type(exc).__name__}: {exc}"
            results.append(row)
            print(f"  ...{agent_id} done")
    finally:
        print("stopping Bonsai llama-server (freeing VRAM)...")
        await bonsai_llm.stop_server()

    # Persist BEFORE printing -- see the stdout note at the top of this file.
    out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "data", "bonsai_probe_results.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)
    print(f"\nresults saved to {out_path}")

    print("\n================ RESULTS ================")
    for r in results:
        head = "OK  " if r.get("ok") else "FAIL"
        print(f"\n[{head}] {r['agent']} -- {r['label']}")
        print(f"        system prompt {r['sys_chars']} chars (~{r['sys_tok_est']} tok), "
              f"structured tools fired: {r['tools_fired'] or 'none'}")
        if not r.get("ok"):
            print(f"        {r['error']}")
            continue
        reply = r["reply"]
        # A text pseudo-tool-call reaching the caller is the failure mode we
        # are hunting -- flag it explicitly rather than making it eyeball work.
        looks_pseudo = ("read_skill" in reply and "```" in reply) or reply.strip().startswith("{")
        print(f"        returned {len(reply)} chars"
              f"{'   <-- LOOKS LIKE A TEXT PSEUDO-TOOL-CALL' if looks_pseudo else ''}")
        print("        ---")
        for line in reply[:900].splitlines():
            print(f"        {line}")


if __name__ == "__main__":
    asyncio.run(main())
