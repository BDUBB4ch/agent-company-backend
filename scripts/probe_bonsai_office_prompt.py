"""
DIAGNOSTIC ONLY -- does Bonsai 27B actually answer a REAL office prompt today?

Why this exists: traces show 8/8 in-office Bonsai calls returned empty, while
the only 2 successes bypassed the agent path. The server log shows the real
failure is an immediate EOS (eval time = 0.00 ms / 1 tokens), NOT the runaway
thinking pass the code comment blames, and --reasoning-budget 1024 did not fix
it. Failures clustered at 3888/3298/1457 prompt tokens while 6642/6235/1871
succeeded, so size is not the variable. That leaves content -- which can only
be settled by sending today's actual prompts.

SAFETY:
  * Writes NOTHING to the brain. No conversations, no facts, no approvals.
    It builds the same system prompt /api/chat would and calls bonsai_llm
    directly, skipping every persistence path.
  * Frees all Ollama VRAM first via llm_router.unload_all_models(), the same
    call the image pipeline uses -- Bonsai (~8GB) must not share the 16GB card.
  * Always stops the llama-server in a finally block so it cannot be left
    holding VRAM if the probe raises.
  * Tools are passed as an empty list so no tool can fire and reach the network.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

import agents          # noqa: E402
import bonsai_llm      # noqa: E402
import llm_router      # noqa: E402
import memory          # noqa: E402

# The three seats that were routed to Bonsai by the global setting, plus a
# tiny control prompt to prove the server itself is healthy when it fails.
SEATS = ["cio", "operations", "marketing"]

QUESTION = (
    "We sell indoor growing supplies to all growers, cannabis included. "
    "Give me two concrete ways to raise repeat purchase rate on nutrients "
    "this quarter. Name the lever for each."
)


def build_office_prompt(agent_id: str) -> str:
    """Same assembly as main.py's /api/chat, minus the live capability block
    (which would need an Ollama round-trip) and the product context."""
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


async def _noop_dispatch(name, args, office_name=None):
    return {"error": "tools disabled during diagnostic probe"}


async def probe(label: str, system_prompt: str, question: str) -> dict:
    result = {"label": label, "sys_chars": len(system_prompt)}
    try:
        reply = await bonsai_llm.call_bonsai(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": question}],
            dispatch_tool_call=_noop_dispatch,
            tools_list=[],
            office_name=None,
        )
        result["ok"] = True
        result["chars"] = len(reply)
        result["preview"] = reply[:400].replace("\n", " ")
    except Exception as exc:  # noqa: BLE001 -- reporting, not handling
        result["ok"] = False
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


async def main():
    print("freeing GPU (unloading all Ollama models)...")
    await llm_router.unload_all_models()

    print("starting Bonsai llama-server...")
    started = await bonsai_llm.ensure_running()
    if not started:
        print("FAILED: Bonsai server did not come up. Nothing else to test.")
        return

    results = []
    try:
        # Control first: a tiny prompt. If this fails the server is broken and
        # nothing about the office prompts can be concluded.
        results.append(await probe("CONTROL (tiny prompt)",
                                   "You are a helpful assistant.",
                                   "Reply with exactly: BONSAI OK"))
        for seat in SEATS:
            sp = build_office_prompt(seat)
            results.append(await probe(f"{seat} (real office prompt)", sp, QUESTION))
    finally:
        print("stopping Bonsai llama-server (freeing VRAM)...")
        await bonsai_llm.stop_server()

    print("\n================ RESULTS ================")
    for r in results:
        status = "OK  " if r.get("ok") else "FAIL"
        print(f"[{status}] {r['label']}  (system prompt {r['sys_chars']} chars)")
        if r.get("ok"):
            print(f"        returned {r['chars']} chars: {r['preview'][:200]}")
        else:
            print(f"        {r['error']}")


if __name__ == "__main__":
    asyncio.run(main())
