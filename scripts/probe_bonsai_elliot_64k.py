"""Can Bonsai hold Elliot at a 64K context window on this 16GB card?

2026-08-16, Barry: "elliot can be switchable too." The recorded blocker:
Elliot's prompt vs BONSAI_NUM_CTX = 32768. After the grammar unpin he is
still ~36-40K tokens base, so the stock window cannot hold him. This probe
answers the empirical question the constant hides: does the MODEL support
a bigger window (n_ctx_train in the server log), does the KV cache fit
16GB alongside ~8GB of weights, and does a real full-sized Elliot prompt
actually answer at usable speed?

Run standalone. Sets BONSAI_NUM_CTX=65536 via env BEFORE importing config,
unloads everything else off the GPU, starts the server, sends Elliot's
REAL composed system prompt plus a question, times it, then stops the
server and prints the log lines that matter.
"""

import asyncio
import io
import os
import sys
import time

os.environ["BONSAI_NUM_CTX"] = "65536"  # must precede config import

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "backend"))

import agents  # noqa: E402
import bonsai_llm  # noqa: E402
import llm_router  # noqa: E402
import memory  # noqa: E402

LOG = os.path.join(BASE, "data", "bonsai_server.log")


def build_elliot_prompt() -> str:
    a = agents.AGENTS["movie"]
    pins = agents.PINNED_SKILLS["movie"]
    return (
        a["system_prompt"]
        + "\n\n" + memory.pinned_skills_block("MovieDirector", pins)
        + "\n--- BUSINESS KNOWLEDGE (the brain) ---\n"
        + memory.brain_context_block("MovieDirector", pinned_titles=pins)
        + "\n--- END BUSINESS KNOWLEDGE ---\n"
    )


async def main():
    prompt = build_elliot_prompt()
    print(f"prompt: {len(prompt):,} chars (~{len(prompt)//4:,}-{int(len(prompt)/3.6):,} tokens)")

    log_start = os.path.getsize(LOG) if os.path.exists(LOG) else 0

    print("unloading everything else off the GPU...")
    await llm_router.unload_all_models()

    print("starting bonsai at ctx 65536...")
    ok = await bonsai_llm.ensure_running()
    print("server up:", ok)
    if not ok:
        return

    t0 = time.time()
    try:
        reply = await bonsai_llm.call_bonsai(
            prompt,
            [{"role": "user", "content":
              "In one paragraph, plain prose: who is Keth and what do his "
              "eyes look like in canon?"}],
            llm_router._dispatch_tool_call,
            tools_list=[],
            office_name="MovieDirector",
        )
        dt = time.time() - t0
        print(f"\nANSWERED in {dt:.1f}s ({len(reply)} chars, {len(reply)/dt:.1f} chars/s)")
        print(reply[:600])
    except Exception as exc:
        print(f"\nFAILED after {time.time()-t0:.1f}s: {type(exc).__name__}: {exc}")

    await bonsai_llm.stop_server()

    # The authoritative facts live in the server's own log.
    if os.path.exists(LOG):
        with open(LOG, encoding="utf-8", errors="replace") as f:
            f.seek(log_start)
            tail = f.read()
        print("\n--- server log (relevant lines) ---")
        for line in tail.splitlines():
            low = line.lower()
            if any(k in low for k in ("n_ctx", "kv cache", "kv self", "vram",
                                       "memory", "buffer size", "failed",
                                       "error", "prompt eval", "eval time",
                                       "tokens per second")):
                print(" ", line.strip()[:150])


if __name__ == "__main__":
    asyncio.run(main())
