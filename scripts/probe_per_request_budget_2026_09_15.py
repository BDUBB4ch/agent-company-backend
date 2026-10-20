"""Does the installed Prism llama-server honour a PER-REQUEST reasoning budget?

Mainline llama.cpp b9982 (July 2026) honours `reasoning_budget_tokens` in the
chat-completions body -- as long as no --reasoning-budget is fixed on the
command line (the 2026-09-08 test set one, which is why every per-request
field looked ignored). This launches the server with the budget UNSET (-1),
sends the same hard question with a 256-token budget and a 4096-token
budget, and compares thinking length and time. Also tries the older alias
`thinking_budget_tokens`. Holds the render flag; restores nothing else --
the office backend launches its own server with its own constant.
"""
import asyncio
import json
import os
import sys
import time

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "backend"))
import bonsai_llm      # noqa: E402
import llm_router      # noqa: E402

FLAG = os.path.join(REPO, "data", "video_rendering.flag")
TOKEN = f"probe-budget-{os.getpid()}"
Q = ("A bottle sells for $60 at a 40% gross margin. A customer uses a 15% off code. "
     "The store pays $9 to ship and the customer pays nothing. What is the store's gross "
     "profit in dollars on that bottle after shipping? Answer with just the number.")


async def one(cx, key, budget):
    body = {"model": "bonsai", "messages": [{"role": "system", "content": "Answer exactly what is asked."},
                                            {"role": "user", "content": Q}],
            "max_tokens": 4096, "temperature": 0.7}
    if key:
        body[key] = budget
    t0 = time.monotonic()
    r = await cx.post("http://127.0.0.1:8811/v1/chat/completions", json=body)
    r.raise_for_status()
    j = r.json()
    msg = j["choices"][0]["message"]
    reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
    usage = j.get("usage", {})
    return {"key": key, "budget": budget, "secs": round(time.monotonic() - t0, 1),
            "reasoning_chars": len(reasoning), "completion_tokens": usage.get("completion_tokens"),
            "answer": (msg.get("content") or "").strip()[:60]}


async def main():
    with open(FLAG, "w", encoding="utf-8") as fh:
        fh.write(TOKEN)
    try:
        await bonsai_llm.stop_server()
        await llm_router.unload_all_models()
        bonsai_llm.REASONING_BUDGET = -1          # "unrestricted" = no server-side budget
        assert await bonsai_llm.ensure_running(), "server did not start"
        async with httpx.AsyncClient(timeout=600) as cx:
            runs = []
            for key, budget in ((None, None), ("reasoning_budget_tokens", 256),
                                ("reasoning_budget_tokens", 4096), ("thinking_budget_tokens", 256)):
                res = await one(cx, key, budget)
                runs.append(res)
                print(f"  {str(key):26} {str(budget):>5} -> thinking {res['reasoning_chars']:>6} chars, "
                      f"{res['completion_tokens']} tokens, {res['secs']}s, answer {res['answer']!r}")
        await bonsai_llm.stop_server()
        with open(os.path.join(REPO, "data", "probe_per_request_budget_2026-09-15.json"), "w", encoding="utf-8") as fh:
            json.dump(runs, fh, indent=2)
        base = runs[0]["reasoning_chars"]; small = runs[1]["reasoning_chars"]; big = runs[2]["reasoning_chars"]
        honoured = small < base * 0.5 and small < big * 0.5
        print("\nVERDICT:", "PER-REQUEST BUDGET HONOURED" if honoured else "IGNORED on this build",
              f"(no budget {base} chars, 256 -> {small}, 4096 -> {big})")
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
