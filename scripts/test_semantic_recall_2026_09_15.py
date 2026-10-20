"""Measure the meaning door (semrecall) before it is switched on.

Runs the EXISTING routing batteries (creative, companionship) with the
semantic door OFF and ON, then a new PARAPHRASE set that the keyword scorer
is known to miss, and the QUIET set that must recall nothing either way.
Also prints the max similarity on every quiet message so SEM_MIN is set
from data, not taste. Read-only against the brain except the fact_vectors
cache table. No model calls, no GPU.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import memory      # noqa: E402
import recall      # noqa: E402
import semrecall   # noqa: E402
import test_creative_routing_2026_09_10 as cre        # noqa: E402
import test_companionship_routing_2026_09_10 as comp  # noqa: E402

PARAPHRASE = [
    # (office, message, substring expected in the top recalled title)
    ("Creative", "the colors clash on the banner, what would you change", "colour"),
    ("Creative", "can you sanity-check the hero pic before it goes up", "qa"),
    ("Creative", "these photos of the tents came out dull", "photograph"),
    ("BusinessOps", "how much runway do we actually have", "cash-flow"),
    ("BusinessOps", "are we making anything on each bottle we sell", "unit-economics"),
    ("BusinessOps", "should we take the loan or not", "funding"),
    ("Marketing", "people open the emails but nobody buys anything", "email"),
    ("Marketing", "our followers never react to anything we post", "social"),
    ("Marketing", "how do we get more people to click the button", "calls-to-action"),
    ("Taliyah", "im venting, dont fix it", "being-there"),
    ("Taliyah", "am i being stupid about this or is it real", "truth"),
    ("MovieDirector", "i want the fight to feel dirtier, more real", "directing"),
]
QUIET = [
    ("BusinessOps", "morning"), ("BusinessOps", "lol you good?"), ("Marketing", "ok cool"),
    ("Creative", "hey whats up"), ("Taliyah", "cant sleep again"), ("Taliyah", "you up?"),
    ("CIO", "say ok"), ("Legal", "thanks man"), ("Engineer", "how was your night"),
]


def set_sem(on: bool) -> None:
    memory.set_setting("semantic_recall", "true" if on else "false")


def top_titles(office: str, msg: str) -> list[str]:
    _block, titles = recall.recall_for_message(office, msg)
    return [t.lower() for t in titles]


def run_existing(name: str, office: str, cases, quiet) -> tuple[int, int, int]:
    ok = 0
    for msg, want in cases:
        t = top_titles(office, msg)
        if t and want.lower() in t[0]:
            ok += 1
    q_ok = sum(1 for msg in quiet if not top_titles(office, msg))
    return ok, len(cases), q_ok


def main() -> None:
    before = memory.get_setting("semantic_recall", "false")
    try:
        for on in (False, True):
            set_sem(on)
            print(f"\n===== semantic door {'ON' if on else 'OFF'} =====")
            ok, n, q = run_existing("creative", cre.OFFICE, cre.CASES, getattr(cre, "QUIET", []))
            print(f"creative battery      {ok}/{n}   quiet clean {q}/{len(getattr(cre, 'QUIET', []))}")
            ok, n, q = run_existing("companionship", comp.OFFICE, comp.CASES, getattr(comp, "QUIET", []))
            print(f"companionship battery {ok}/{n}   quiet clean {q}/{len(getattr(comp, 'QUIET', []))}")
            hits = 0
            for office, msg, want in PARAPHRASE:
                t = top_titles(office, msg)
                got = bool(t) and want in t[0]
                hits += got
                print(f"  {'PASS' if got else 'MISS'} {office:14} {msg[:48]!r:52} -> {t[:2]}")
            print(f"paraphrase set        {hits}/{len(PARAPHRASE)}")
            quiet_bad = [(o, m, top_titles(o, m)) for o, m in QUIET if top_titles(o, m)]
            print(f"quiet set clean       {len(QUIET)-len(quiet_bad)}/{len(QUIET)}"
                  + (f"   LEAKS: {quiet_bad}" if quiet_bad else ""))

        # Calibration view: the highest similarity any quiet message reaches.
        print("\n===== max similarity on quiet messages (SEM_MIN =", semrecall.SEM_MIN, ") =====")
        for office, msg in QUIET:
            facts = [f for f in memory.get_active_facts_for_agent(office) if memory._is_skill_fact(f)
                     and not (f.get("source_name") or "").startswith(("mind-", "worknote-"))]
            sims = semrecall.similarities(msg, facts)
            if sims:
                fid, s = max(sims.items(), key=lambda x: x[1])
                title = next(memory._skill_title(f) for f in facts if int(f["id"]) == fid)
                print(f"  {s:.3f}  {office:12} {msg!r:22} -> {title}")
    finally:
        memory.set_setting("semantic_recall", before or "false")
        print(f"\nsemantic_recall restored to {before or 'false'}")


if __name__ == "__main__":
    main()
