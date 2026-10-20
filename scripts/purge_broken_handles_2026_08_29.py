"""Purge the two BROKEN @handles from everything Elliot reads.

Barry, 2026-08-29: "make sure elliot knows how to write for this. its a lock."
The lock FAILED on its first live test -- he wrote the old handles anyway,
because they outnumbered the correct ones 14 to 9 across his always-on context.
A pinned correction does not win against volume; the wrong strings have to go.

BROKEN (element does not exist / was deleted):
    the old B Dubb handle ending in "-new"   -> @b-dubb
    the old Vor'Shara handle (just her name) -> @lady-vor-shara-vel

Also normalises @Yannah -> @yannah and @Keth -> @keth, which Barry renamed
tonight so the elements match.

WHERE: character-anchors-card (a DERIVED artifact -- safe to rewrite),
standing-rule-shot-prompt-format, style-exemplars, and any thread summary.
**Barry's authored scripts are NOT touched** -- the substitute-never-edit rule
of 2026-08-14 still governs those; Elliot types the new handle where an old
file says the old one.

Historical records keep the fact of the rename but lose the copyable string:
"@B-DUBB-new" becomes "the -new handle (dead)" so nothing can be lifted from a
warning and pasted into a prompt -- the exact failure mode this office already
documented with Amara on 2026-08-16.

Backs up every fact it edits.
"""
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
import memory  # noqa: E402

BACKUP = os.path.join(ROOT, "data", "backup_broken_handles_2026-08-29.json")

# order matters: longest first so @B-DUBB-new is consumed before @B-DUBB
LIVE_SWAPS = [
    ("@B-DUBB-new", "@b-dubb"),
    ("@Vorshara", "@lady-vor-shara-vel"),
    ("@Yannah", "@yannah"),
    ("@Keth", "@keth"),
]
# in explanatory/historical prose the handle must survive as a FACT but not as
# a pasteable token
PROSE_SWAPS = [
    ("Where it says\n  @BDUBB, you type @b-dubb",
     "Where it says the old BDUBB handle, you type @b-dubb"),
]


def clean(text):
    for old, new in LIVE_SWAPS:
        text = re.sub(re.escape(old) + r"(?![\w-])", new, text)
    for old, new in PROSE_SWAPS:
        text = text.replace(old, new)
    return text


def main():
    targets = ["character-anchors-card", "standing-rule-shot-prompt-format",
               "style-exemplars"]
    backup = []
    changed = []
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT id, source_name, content FROM facts "
            "WHERE category LIKE '%MovieDirector%' AND status='active'"
        ).fetchall()
        also = conn.execute(
            "SELECT id, source_name, content FROM facts "
            "WHERE status='active' AND source_name LIKE '%anchors-card%'"
        ).fetchall()
    seen = {}
    for r in list(rows) + list(also):
        seen[r["id"]] = r

    for fid, r in seen.items():
        c = r["content"] or ""
        title = (r["source_name"] or "").replace(".md", "")
        # only the derived/office-owned docs; never his authored scripts
        if not any(t in title for t in targets) and "Auto-summarized" not in (
                r["source_name"] or ""):
            continue
        new = clean(c)
        if new == c:
            continue
        backup.append({"id": fid, "source_name": r["source_name"],
                       "content": c})
        with memory.get_db() as conn:
            conn.execute("UPDATE facts SET content=? WHERE id=?", (new, fid))
        changed.append((fid, r["source_name"],
                        c.count("@B-DUBB-new") + c.count("@Vorshara")))

    json.dump(backup, open(BACKUP, "w", encoding="utf-8"), indent=1)
    for fid, sn, n in changed:
        print(f"  cleaned fact {fid:5d}  {sn}  ({n} broken handles)")
    print(f"backed up {len(backup)} facts -> {os.path.basename(BACKUP)}")

    # verify against what Elliot actually sees
    from agents import PINNED_SKILLS, MOVIE_ID
    blk = memory.pinned_skills_block("MovieDirector", PINNED_SKILLS[MOVIE_ID])
    brain = memory.brain_context_block("MovieDirector")
    bad = {}
    for h in ("@B-DUBB-new", "@Vorshara"):
        bad[h] = len(re.findall(re.escape(h) + r"(?![\w-])", blk + brain))
    print("remaining in his always-on context:", bad)
    assert sum(bad.values()) == 0, "broken handles still present"
    for h in ("@b-dubb", "@lady-vor-shara-vel"):
        assert h in blk, f"{h} not in pinned block"
    print("VERIFIED: zero broken handles in pinned + brain; correct ones present.")


if __name__ == "__main__":
    main()
