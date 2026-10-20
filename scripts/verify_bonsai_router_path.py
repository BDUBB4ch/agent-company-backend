"""
Final pre-switch check: does the FULL router path (not just call_bonsai)
answer on Bonsai without silently falling back to Ollama?

The probes so far called bonsai_llm.call_bonsai directly. llm_router.generate()
adds the VRAM unload chain, ensure_running, the circuit breaker and the
Ollama fallback. `llm_router.bonsai_fell_back()` is the flag /api/chat returns
to the dashboard, so it is the honest measure of "Bonsai actually answered".

Covers only the three seats a global switch affects -- cio, operations,
marketing. Everyone else is pinned by AGENT_OLLAMA_MODEL_OVERRIDES:
business/legal on the 14b, engineer on the coder, and creative/movie/taliyah
on the 9b (which is why Elliot's 29.3K prompt never meets Bonsai's 32K ctx).

SAFETY: no brain writes -- goes through the router, not main.py's /api/chat,
so no conversations, no facts, no Priya mirror. Web search off.
"""
import asyncio
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

import agents          # noqa: E402
import llm_router      # noqa: E402
import memory          # noqa: E402

SEATS = ["cio", "operations", "marketing"]
QUESTION = ("Give me one concrete way to raise repeat purchase rate on "
            "nutrients this quarter. Name the lever.")


def build_prompt(agent_id: str) -> str:
    a = agents.AGENTS[agent_id]
    off = a["office_name"]
    pins = agents.pinned_skills_for(agent_id)
    return (
        f"{a['system_prompt']}\n\n{memory.pinned_skills_block(off, pins)}\n"
        f"--- BUSINESS KNOWLEDGE (the brain) ---\n"
        f"{memory.brain_context_block(off, include_shared=True, pinned_titles=pins)}\n"
        f"--- END BUSINESS KNOWLEDGE ---"
    )


async def main():
    backend, model = memory.get_active_generation()
    print(f"active setting: backend={backend} model={model}\n")

    ok = True
    for seat in SEATS:
        office = agents.AGENTS[seat]["office_name"]
        log = []
        t0 = time.monotonic()
        try:
            reply = await llm_router.generate(
                backend=backend,
                system_prompt=build_prompt(seat),
                messages=[{"role": "user", "content": QUESTION}],
                model=model,
                use_tools=True,
                allow_web_search=False,
                tool_call_log=log,
                office_name=office,
            )
            secs = time.monotonic() - t0
            fell_back = llm_router.bonsai_fell_back()
            if fell_back:
                ok = False
            print(f"{seat:11} {secs:5.1f}s  fell_back={fell_back}  "
                  f"tools={log or 'none'}  {len(reply)} chars")
            print(f"            {reply[:150].replace(chr(10), ' ')}")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"{seat:11} ERROR {type(exc).__name__}: {exc}")

    print()
    print("VERDICT:", "Bonsai answered every seat with no fallback."
          if ok else "NOT CLEAN -- at least one seat fell back or errored.")


if __name__ == "__main__":
    asyncio.run(main())
