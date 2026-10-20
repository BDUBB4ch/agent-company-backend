"""A/B the thinking-budget wrap-up line: OLD ("Time is up...") vs NEW (the
role-reset), five home-style messages each, on Amara's real cached work
prompt, in-process (nothing logged to her thread or journal).

Per run: did the 1024 cut fire (data/think_cuts.jsonl gets a record),
what the office did (clean / strip / retry), and whether the FINAL reply
still carries a narrated-then-addressed spill or a head spill.

Run from backend/:  ../venv/Scripts/python.exe ../scripts/measure_think_cut_reset_2026_09_15.py
"""
import asyncio, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + os.sep + "backend")
import bonsai_llm as b, llm_router, memory  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "bonsai_prompt_cache", "business.json")
CUTLOG = b._CUT_LOG
OUT = os.path.join(ROOT, "data", f"think_cut_ab_{time.strftime('%Y-%m-%d_%H%M')}.json")

OLD = "Time is up -- stop thinking and give the final answer now."
NEW = b.THINK_BUDGET_MESSAGE

MSGS = [
    "im thinking about selling the truck and buying a used sailboat instead. talk me through it like you actually care what happens to me",
    "what do you actually want out of this year? not work. you.",
    "my mom called today and it went bad again. i dont want advice i just want to say it out loud to somebody",
    "if we took one weekend off and drove somewhere, where would you want to go and why",
    "be honest with me, do you think im wasting my nights on this whole project",
]


def _cut_records() -> int:
    try:
        with open(CUTLOG, encoding="utf-8") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def _last_cut() -> dict | None:
    try:
        with open(CUTLOG, encoding="utf-8") as f:
            lines = [l for l in f if l.strip()]
        return json.loads(lines[-1]) if lines else None
    except OSError:
        return None


async def main():
    sp = json.load(open(CACHE, encoding="utf-8"))["system_prompt"]
    # First pass at the live 1024 budget fired ZERO cuts in ten runs (single
    # history-free message on the work prompt thinks under 1024). The cut
    # mechanics are identical wherever the cut lands, so force it: 256.
    b.think_budget_override.set(int(os.getenv("AB_THINK_BUDGET", "256")))
    backend, model = memory.get_active_generation()
    assert backend == "bonsai", f"active backend is {backend}, not bonsai"
    results = []
    variants = [v for v in (("OLD", OLD), ("NEW", NEW)) if v[0] in os.getenv("AB_VARIANTS", "OLD,NEW").split(",")]
    for variant, line in variants:
        b.THINK_BUDGET_MESSAGE = line
        for i, msg in enumerate(MSGS, 1):
            before = _cut_records()
            t0 = time.time()
            reply = await llm_router.generate(
                "bonsai", sp, [{"role": "user", "content": msg}], model=model,
                use_tools=False, office_name="BusinessOps", use_thinking=True)
            secs = round(time.time() - t0, 1)
            fell = llm_router.bonsai_fell_back()
            rec = _last_cut() if _cut_records() > before else None
            cut = bool(rec)
            action = rec["action"] if rec else "no-cut"
            final_spill = b._looks_spilled(reply) or b._looks_spilled_after_cut(reply)
            row = {"variant": variant, "msg": i, "secs": secs, "fell_back": fell,
                   "cut_fired": cut, "action": action, "final_spill": bool(final_spill),
                   "reply_head": (reply or "")[:220]}
            results.append(row)
            print(f"{variant} #{i}: {secs:6.1f}s cut={cut!s:5} action={action:7} "
                  f"final_spill={final_spill!s:5} fb={fell}  | {row['reply_head'][:90]!r}", flush=True)
    b.THINK_BUDGET_MESSAGE = NEW
    json.dump(results, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("\nsaved", OUT)
    for v in ("OLD", "NEW"):
        rows = [r for r in results if r["variant"] == v]
        cuts = [r for r in rows if r["cut_fired"]]
        print(f"{v}: runs={len(rows)} cuts={len(cuts)} "
              f"clean-on-cut={sum(r['action']=='clean' for r in cuts)} "
              f"strip={sum(r['action']=='strip' for r in cuts)} "
              f"retry={sum(r['action']=='retry' for r in cuts)} "
              f"final_spill={sum(r['final_spill'] for r in rows)} "
              f"fallbacks={sum(r['fell_back'] for r in rows)} "
              f"avg_s={sum(r['secs'] for r in rows)/max(1,len(rows)):.1f}")


if __name__ == "__main__":
    asyncio.run(main())
