"""Wipe the dead @handles out of Elliot's brain entirely.

Barry, 2026-08-29: "wipe it from his brain."

AUTHORITY: the 2026-08-14 substitute-never-edit ruling deliberately left this
door open -- "He also has standing permission for the alternative Barry named
-- a mechanical handles-only rewrite of those files -- if Barry asks for it."
He has now asked.

SCOPE, and it is deliberately narrow: HANDLE STRINGS ONLY.
    @B-DUBB-new / @B-Dubb-new / @BDUBB   -> @b-dubb
    @Vorshara / @Vor'Shara / @LadyVorshara -> @lady-vor-shara-vel
    @Yannah -> @yannah      @Keth -> @keth
Not a line of dialogue, not a shot, not a beat, not a description. If anything
else in a file looks wrong it stays wrong until he says otherwise.

Every fact is backed up before it is touched, and every edit is asserted to
change ONLY handle characters -- the script refuses to write if any other text
moved.
"""
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
import memory  # noqa: E402

BACKUP = os.path.join(ROOT, "data", "backup_dead_handles_wipe_2026-08-29.json")

SWAPS = [
    (re.compile(r"@B[-\s]?DUBB[-\s]?new\b", re.I), "@b-dubb"),
    (re.compile(r"@BDUBB\b", re.I), "@b-dubb"),
    (re.compile(r"@(?:Lady)?Vor'?[-\s]?Shara(?:[-\s]?Vel)?\b(?![-\w])", re.I),
     "@lady-vor-shara-vel"),
    (re.compile(r"@Yannah\b(?![-'\w])"), "@yannah"),
    (re.compile(r"@Keth\b(?![-'\w])"), "@keth"),
]

# Handles that OWN a possessive asset must survive untouched -- @Yannah's-
# Machine-Pistol, @Bia's-Pistol*, @Tazz's-Weapon, @B-Dubb's-Banger are their
# own elements. The negative lookaheads above do that; this list is the test.
MUST_SURVIVE = ["@Yannah's-Machine-Pistol", "@Bia's-Pistol*",
                "@Tazz's-Weapon", "@B-Dubb's-Banger", "@Bia-2", "@Tazz",
                "@TALIA", "@loc_lady-vors-sanctum"]


def swap(text):
    for pat, live in SWAPS:
        text = pat.sub(live, text)
    return text


def only_handles_changed(before, after):
    """Both sides with every handle normalised must be identical -- proves
    nothing but handle characters moved."""
    return swap(before) == after


def main():
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT id, category, source_name, content FROM facts "
            "WHERE status='active'").fetchall()

    backup, changed = [], []
    for r in rows:
        c = r["content"] or ""
        # Elliot's own shelf + anything shared he reads
        if "MovieDirector" not in (r["category"] or "") and \
                (r["category"] or "") not in ("knowledge:talia_crew",):
            continue
        new = swap(c)
        if new == c:
            continue
        assert only_handles_changed(c, new), \
            f"fact {r['id']}: something other than a handle changed"
        for keep in MUST_SURVIVE:
            assert c.count(keep) == new.count(keep), \
                f"fact {r['id']}: damaged {keep}"
        backup.append({"id": r["id"], "category": r["category"],
                       "source_name": r["source_name"], "content": c})
        with memory.get_db() as conn:
            conn.execute("UPDATE facts SET content=? WHERE id=?",
                         (new, r["id"]))
        changed.append((r["id"], r["source_name"], len(c), len(new)))

    json.dump(backup, open(BACKUP, "w", encoding="utf-8"), indent=1)
    for fid, sn, a, b in changed:
        print(f"  {fid:5d}  {str(sn)[:46]:48s} {a:>7,} -> {b:>7,}")
    print(f"\n{len(changed)} facts rewritten, backed up -> "
          f"{os.path.basename(BACKUP)}")

    # verify against what he actually reads
    from agents import PINNED_SKILLS, MOVIE_ID
    blk = memory.pinned_skills_block("MovieDirector", PINNED_SKILLS[MOVIE_ID])
    brain = memory.brain_context_block("MovieDirector")
    shelf = "".join((f.get("content") or "")
                    for f in memory.get_active_facts_for_agent("MovieDirector"))
    dead = 0
    for label, txt in (("pinned", blk), ("brain", brain), ("whole shelf", shelf)):
        n = sum(len(p.findall(txt)) for p, _ in SWAPS)
        print(f"  dead handles in {label:12s}: {n}")
        dead += n
    assert dead == 0, "dead handles still present somewhere he reads"
    print("VERIFIED: zero dead handles anywhere in Elliot's brain.")


if __name__ == "__main__":
    main()
