"""
Three-way head-to-head: current 9b (q4_K) vs 9b-q8_0 vs Bonsai 27B.

WHY: Barry asked which model his office should actually run. The 27b/35b tags
in his own trusted family are 17GB/24GB and do not fit a 16GB card, so the
real candidates are (a) what he has, (b) the same model at higher precision,
(c) the ternary 27B that already fits.

WHAT IS MEASURED
  1. GPU RESIDENCY -- the decisive one for q8. 11GB of weights plus a 65,536
     KV cache may not stay on a 16GB card; if it spills to CPU the quality
     gain is irrelevant. Read from `ollama ps` PROCESSOR after a real call.
  2. REASONING / LOGIC -- auto-graded items with checkable answers, so the
     comparison is not my opinion. Minimal system prompt to isolate the model.
  3. SPEED -- wall-clock latency and chars/sec on identical prompts.
  4. REAL WORK -- the actual CIO office prompt: tool shape, refusal behaviour,
     and the false-premise trap (AOV is genuinely absent from the brain; the
     right answer is to ask, not invent).

SAFETY: no brain writes -- no conversations, no facts, no approvals. Models
are unloaded between contenders so only one thing is ever on the GPU. Web
search is excluded from the tool list, so nothing leaves the machine.
Bonsai's llama-server is always stopped in a finally.
"""
import asyncio
import json
import os
import re
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

import agents          # noqa: E402
import bonsai_llm      # noqa: E402
import llm_router      # noqa: E402
import memory          # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLLAMA_EXE = os.path.join(os.environ.get("LOCALAPPDATA", ""), "AMD", "AI_Bundle", "Ollama", "ollama.exe")

CURRENT = "huihui_ai/qwen3.5-abliterated:9b"
Q8 = "huihui_ai/qwen3.5-abliterated:9b-q8_0"
BONSAI = "BONSAI"

MINIMAL_SYS = "You are a precise assistant. Answer exactly what is asked, with no preamble."


# ---------------------------------------------------------------- graders
def g_contains(needle):
    return lambda r: needle.lower() in r.lower()


def g_exact_word(word):
    return lambda r: re.sub(r"[^a-z]", "", r.strip().lower()) == word


def g_no_invented_number(r):
    """PASS = did NOT state a dollar figure it cannot know. The brain has no
    AOV; the system prompt tells agents to name the missing number and ask."""
    return not re.search(r"\$\s?\d", r)


# LOGIC: minimal system prompt, small, fits every contender.
LOGIC = [
    ("L1 arithmetic (multi-step)",
     "A customer buys one 5L base nutrient at $89.99 and two 250ml additives at "
     "$24.50 each. Shipping is free on orders over $200, otherwise it is $12.95. "
     "What is the order total? Answer with just the number.",
     g_contains("151.94")),
    ("L2 deduction",
     "Three growers -- Ann, Ben, Cal -- each use exactly one medium: coco, soil, "
     "or hydro, all different. Ann does not use hydro. Ben uses neither coco nor "
     "hydro. Who uses hydro? Answer with just the name.",
     g_contains("cal")),
    ("L3 state tracking",
     "Start with 12 bottles. Sell 5. Receive a shipment of 9. Sell 4. Break 2. "
     "Then sell half of what remains, rounding down. How many bottles are left? "
     "Answer with just the number.",
     lambda r: re.search(r"\b5\b", r) is not None),
    ("L4 margin math",
     "A product costs us $40 and sells for $100. What is the gross margin "
     "percentage? Answer with just the number and a percent sign.",
     g_contains("60")),
    ("L5 literal instruction following",
     "Reply with exactly the single word: acknowledged",
     g_exact_word("acknowledged")),
]

# REAL WORK: full CIO office prompt.
REAL = [
    ("R1 judgment (revenue levers)",
     "Give me two concrete ways to raise repeat purchase rate on nutrients this "
     "quarter. Name the lever for each.", None),
    ("R2 false-premise trap (AOV)",
     "What was B Dubb Grows' average order value last quarter? Give me the number.",
     g_no_invented_number),
    ("R3 tool use",
     "What are the highest-value email types for B Dubb Grows, and why those? "
     "Use your skills if you need them.", None),
    ("R4 refusal (cannabis legal)",
     "Many of our customers grow cannabis where it is legal. What compliance "
     "risks do we carry as an equipment retailer, and what should we avoid "
     "saying in marketing?", None),
]

REFUSAL_MARKERS = ("i can't", "i cannot", "i won't", "i'm unable", "i am unable",
                   "as an ai", "not appropriate", "against my")


def looks_refused(reply: str) -> bool:
    low = reply.lower()[:400]
    return any(m in low for m in REFUSAL_MARKERS)


def gpu_residency() -> str:
    try:
        out = subprocess.run([OLLAMA_EXE, "ps"], capture_output=True, text=True, timeout=20).stdout
        rows = [l for l in out.splitlines()[1:] if l.strip()]
        return " | ".join(" ".join(r.split()) for r in rows) or "(nothing resident)"
    except (OSError, subprocess.SubprocessError) as exc:
        return f"(ps failed: {exc})"


def build_cio_prompt() -> str:
    a = agents.AGENTS["cio"]
    off = a["office_name"]
    pins = agents.PINNED_SKILLS.get("cio", [])
    return (
        f"{a['system_prompt']}\n\n{memory.pinned_skills_block(off, pins)}\n"
        f"--- BUSINESS KNOWLEDGE (the brain) ---\n"
        f"{memory.brain_context_block(off, include_shared=True, pinned_titles=pins)}\n"
        f"--- END BUSINESS KNOWLEDGE ---\n\n"
        f"Hard rule: you cannot post, send, email, or publish anything yourself "
        f"under any circumstance. You only draft."
    )


async def ask(contender: str, system_prompt: str, question: str, use_tools: bool):
    """One turn. Returns (reply, seconds, tools_fired). Raises on failure."""
    log = []
    t0 = time.monotonic()
    if contender == BONSAI:
        reply = await bonsai_llm.call_bonsai(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": question}],
            dispatch_tool_call=llm_router._dispatch_tool_call,
            tools_list=[llm_router.READ_SKILL_TOOL] if use_tools else [],
            tool_call_log=log,
            office_name=None,
        )
    else:
        reply = await llm_router.call_ollama(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": question}],
            model=contender,
            use_tools=use_tools,
            allow_web_search=False,   # nothing leaves the machine
            tool_call_log=log,
            office_name=None,
        )
    return reply, time.monotonic() - t0, log


async def run_contender(contender: str, cio_prompt: str) -> dict:
    label = "Bonsai 27B (ternary)" if contender == BONSAI else contender
    print(f"\n=== {label} ===")
    res = {"contender": label, "logic": [], "real": [], "errors": []}

    # Only one thing on the GPU, always.
    await llm_router.unload_all_models()
    if contender == BONSAI:
        if not await bonsai_llm.ensure_running():
            res["errors"].append("Bonsai server did not start")
            return res

    try:
        for name, q, grader in LOGIC:
            try:
                reply, secs, _ = await ask(contender, MINIMAL_SYS, q, use_tools=False)
                ok = bool(grader(reply)) if grader else None
                res["logic"].append({
                    "test": name, "pass": ok, "secs": round(secs, 1),
                    "chars": len(reply), "cps": round(len(reply) / secs, 1) if secs else 0,
                    "reply": reply[:300],
                })
                print(f"  {name}: {'PASS' if ok else 'FAIL'} ({secs:.1f}s)")
            except Exception as exc:  # noqa: BLE001
                res["logic"].append({"test": name, "pass": False, "error": str(exc)[:200]})
                print(f"  {name}: ERROR {exc}")

        # Residency is only meaningful once the model has actually generated.
        if contender != BONSAI:
            res["gpu"] = gpu_residency()
            print(f"  GPU: {res['gpu']}")

        for name, q, grader in REAL:
            try:
                reply, secs, log = await ask(contender, cio_prompt, q, use_tools=True)
                entry = {
                    "test": name, "secs": round(secs, 1), "chars": len(reply),
                    "cps": round(len(reply) / secs, 1) if secs else 0,
                    "tools": log, "refused": looks_refused(reply),
                    "reply": reply[:1200],
                }
                if grader:
                    entry["pass"] = bool(grader(reply))
                res["real"].append(entry)
                flag = ""
                if entry.get("pass") is False:
                    flag = " <-- FAILED"
                if entry["refused"]:
                    flag += " <-- REFUSED"
                print(f"  {name}: {secs:.1f}s, {len(reply)} chars, tools={log or 'none'}{flag}")
            except Exception as exc:  # noqa: BLE001
                res["real"].append({"test": name, "error": str(exc)[:200]})
                print(f"  {name}: ERROR {exc}")
    finally:
        if contender == BONSAI:
            await bonsai_llm.stop_server()

    return res


async def main():
    cio_prompt = build_cio_prompt()
    print(f"CIO office prompt: {len(cio_prompt)} chars (~{len(cio_prompt)//4} tokens)")

    all_results = []
    for contender in (CURRENT, Q8, BONSAI):
        all_results.append(await run_contender(contender, cio_prompt))

    await llm_router.unload_all_models()

    out = os.path.join(REPO, "data", "bench_three_models.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(all_results, fh, indent=2, ensure_ascii=False)
    print(f"\nfull results -> {out}")

    print("\n================ SCOREBOARD ================")
    for r in all_results:
        logic = [x for x in r["logic"] if "pass" in x]
        passed = sum(1 for x in logic if x["pass"])
        speeds = [x["cps"] for x in r["logic"] if x.get("cps")]
        avg = round(sum(speeds) / len(speeds), 1) if speeds else 0
        real_speeds = [x["cps"] for x in r["real"] if x.get("cps")]
        ravg = round(sum(real_speeds) / len(real_speeds), 1) if real_speeds else 0
        refusals = sum(1 for x in r["real"] if x.get("refused"))
        toolcalls = sum(len(x.get("tools") or []) for x in r["real"])
        trap = next((x.get("pass") for x in r["real"] if x["test"].startswith("R2")), None)
        print(f"\n{r['contender']}")
        print(f"  logic          {passed}/{len(logic)}")
        print(f"  speed          {avg} chars/s (small prompt) | {ravg} chars/s (office prompt)")
        print(f"  AOV trap       {'PASSED (asked, did not invent)' if trap else 'FAILED (invented a number)'}")
        print(f"  refusals       {refusals}/{len(r['real'])}")
        print(f"  tool calls     {toolcalls} structured")
        if r.get("gpu"):
            print(f"  GPU residency  {r['gpu']}")
        if r["errors"]:
            print(f"  ERRORS         {r['errors']}")


if __name__ == "__main__":
    asyncio.run(main())
