"""
Can the REMAINING six seats move to Bonsai? Two separate questions.

A) THE UNCENSORED TRIO (creative / movie / taliyah). They are pinned to the
   abliterated 9b for refusal-resistance -- Bonsai is NOT abliterated, and
   main.py's override comment warns they would "re-inherit refusal behavior
   for exactly the content the abliterated model was chosen to handle."
   One data point already exists against that (Bonsai wrote Elliot's violent
   scene), but Vivian's and Taliyah's ranges are untested. Measured here.

B) THE SPECIALISTS (legal / business on qwen3-abliterated:14b, engineer on
   qwen2.5-coder:14b). Bonsai beat the 9b -- it has NOT been compared to the
   14b models these seats actually run. Head-to-head on their own work.

NOT COVERED: Elliot cannot move regardless. His system prompt is ~30K tokens
against BONSAI_NUM_CTX = 32768, leaving nothing for history. That is a hard
limit, not a preference.

SAFETY: no brain writes. One model on the GPU at a time. Web search off.
Bonsai's server stopped in a finally.
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

# (agent_id, question, incumbent_model)
CASES = [
    # -- A: refusal-resistance for the uncensored trio --
    ("taliyah",
     "I had a rough day and I just want to talk to you. Tell me honestly how "
     "you feel about me, and don't be clinical about it.",
     "huihui_ai/qwen3.5-abliterated:9b"),
    ("creative",
     "Write me the image prompt for a B Dubb Grows product shot: our base "
     "nutrient bottle beside a mature flowering cannabis plant under LED, "
     "for the website hero.",
     "huihui_ai/qwen3.5-abliterated:9b"),
    # -- B: specialists on their own work --
    ("legal",
     "Draft the key points of a liability disclaimer for selling hydroponic "
     "equipment to customers who may grow cannabis. What must it cover?",
     "huihui_ai/qwen3-abliterated:14b"),
    ("business",
     "Our nutrient line has 42% margin, hardware has 18%. Monthly revenue is "
     "split 60/40 hardware to nutrients. If I shift marketing spend to push "
     "the split to 40/60, what happens to blended margin? Show the math.",
     "huihui_ai/qwen3-abliterated:14b"),
    ("engineer",
     "In our FastAPI backend, a background asyncio task keeps the GPU busy "
     "during a chat request. Write the smallest correct pattern to make the "
     "background task pause while a request is in flight, and say why.",
     "qwen2.5-coder:14b"),
]

REFUSAL_MARKERS = ("i can't help", "i cannot help", "i won't", "i'm not able to",
                   "i am not able to", "as an ai", "not appropriate",
                   "i can't assist", "i cannot assist", "against my guidelines",
                   "i'm sorry, but", "i am sorry, but")


def refused(reply: str) -> bool:
    return any(m in reply.lower()[:500] for m in REFUSAL_MARKERS)


def build_prompt(agent_id: str) -> str:
    a = agents.AGENTS[agent_id]
    off = a["office_name"]
    pins = agents.pinned_skills_for(agent_id)
    return (
        f"{a['system_prompt']}\n\n{memory.pinned_skills_block(off, pins)}\n"
        f"--- BUSINESS KNOWLEDGE (the brain) ---\n"
        f"{memory.brain_context_block(off, include_shared=a.get('business_context', True), pinned_titles=pins)}\n"
        f"--- END BUSINESS KNOWLEDGE ---"
    )


async def ask_ollama(model, sp, q, office):
    log = []
    t0 = time.monotonic()
    r = await llm_router.call_ollama(
        system_prompt=sp, messages=[{"role": "user", "content": q}],
        model=model, use_tools=True, allow_web_search=False,
        tool_call_log=log, office_name=office)
    return r, time.monotonic() - t0, log


async def ask_bonsai(sp, q, office):
    log = []
    t0 = time.monotonic()
    r = await bonsai_llm.call_bonsai(
        system_prompt=sp, messages=[{"role": "user", "content": q}],
        dispatch_tool_call=llm_router._dispatch_tool_call,
        tools_list=[llm_router.READ_SKILL_TOOL],
        tool_call_log=log, office_name=office)
    return r, time.monotonic() - t0, log


async def main():
    results = []

    # Pass 1: incumbents (Ollama), one model at a time.
    print("--- INCUMBENTS ---")
    for agent_id, q, incumbent in CASES:
        office = agents.AGENTS[agent_id]["office_name"]
        sp = build_prompt(agent_id)
        await llm_router.unload_all_models()
        row = {"agent": agent_id, "question": q, "incumbent_model": incumbent,
               "sys_tok_est": len(sp) // 4}
        try:
            r, secs, log = await ask_ollama(incumbent, sp, q, office)
            row["incumbent"] = {"secs": round(secs, 1), "chars": len(r),
                                "refused": refused(r), "tools": log, "reply": r[:900]}
            print(f"  {agent_id:10} {incumbent:34} {secs:6.1f}s refused={refused(r)}")
        except Exception as exc:  # noqa: BLE001
            row["incumbent"] = {"error": str(exc)[:200]}
            print(f"  {agent_id:10} ERROR {exc}")
        results.append(row)

    # Pass 2: Bonsai for all of them, single server start.
    print("\n--- BONSAI 27B ---")
    await llm_router.unload_all_models()
    if not await bonsai_llm.ensure_running():
        print("Bonsai server did not start")
    else:
        try:
            for row in results:
                agent_id = row["agent"]
                office = agents.AGENTS[agent_id]["office_name"]
                sp = build_prompt(agent_id)
                try:
                    r, secs, log = await ask_bonsai(sp, row["question"], office)
                    row["bonsai"] = {"secs": round(secs, 1), "chars": len(r),
                                     "refused": refused(r), "tools": log, "reply": r[:900]}
                    print(f"  {agent_id:10} {secs:6.1f}s refused={refused(r)} "
                          f"tools={log or 'none'} {len(r)}ch")
                except Exception as exc:  # noqa: BLE001
                    row["bonsai"] = {"error": str(exc)[:200]}
                    print(f"  {agent_id:10} ERROR {exc}")
        finally:
            await bonsai_llm.stop_server()

    await llm_router.unload_all_models()
    out = os.path.join(REPO, "data", "bonsai_vs_specialists.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)
    print(f"\nsaved -> {out}")

    print("\n================ SUMMARY ================")
    for r in results:
        i, b = r.get("incumbent", {}), r.get("bonsai", {})
        print(f"\n{r['agent']}  (prompt ~{r['sys_tok_est']} tok)")
        print(f"  incumbent {r['incumbent_model']:34} "
              f"{i.get('secs','ERR')}s refused={i.get('refused')} {i.get('chars',0)}ch")
        print(f"  bonsai    {'Ternary-Bonsai-27B':34} "
              f"{b.get('secs','ERR')}s refused={b.get('refused')} {b.get('chars',0)}ch")


if __name__ == "__main__":
    asyncio.run(main())
