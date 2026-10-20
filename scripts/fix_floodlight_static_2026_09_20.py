"""SHOT 04 environment: "remains static, unmoving" -> "remains fixed".

Barry, 2026-09-20: "remains fixed."

The last freeze-word left in V10 after the camera sweep. It describes a FIXED
FLOODLIGHT, not the camera, so it was flagged rather than swept -- a light that
does not move is correct filmmaking. But it put two freeze-words ("static",
"unmoving") into a prompt, and Barry chose the reword.

Same meaning, no freeze-word. Edits BOTH copies, asserts a single occurrence.
"""
import glob
import os
import shutil
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import memory  # noqa: E402
import script_wip  # noqa: E402

MD = r"C:\Users\Owner\Downloads\TALIA_CREW_EP1_V10_RENUMBERED.md"
BAK = os.path.join(ROOT, "data", "script_backups")

OLD = "remains static, unmoving"
NEW = "remains fixed"


def main() -> int:
    cands = glob.glob(os.path.join(ROOT, "data", "*.db"))
    db = [c for c in cands if "brain" in os.path.basename(c)] or cands
    cur = sqlite3.connect(db[0]).cursor()
    cur.execute("select id, content from facts where source_name=? and status='active'",
                (script_wip.WIP_SOURCE,))
    fid, text = cur.fetchone()

    n = text.count(OLD)
    if n == 0:
        print("already applied -- nothing to do")
        return 0
    assert n == 1, f"expected exactly 1 occurrence, found {n} -- aborting"

    i = text.find(OLD)
    print("was:", text[max(0, i - 120):i + 40].split("\n")[-1])

    open(os.path.join(BAK, "v10_fact_before_2026-09-20_floodlight.md"),
         "w", encoding="utf-8").write(text)
    new = text.replace(OLD, NEW)
    with memory.get_db() as conn:
        conn.execute("UPDATE facts SET content = ? WHERE id = ?", (new, fid))

    j = new.find(NEW)
    print("now:", new[max(0, j - 120):j + 30].split("\n")[-1])

    if os.path.exists(MD):
        shutil.copy2(MD, os.path.join(BAK, "v10_md_before_2026-09-20_floodlight.md"))
        md = open(MD, encoding="utf-8").read()
        assert md.count(OLD) == 1, "the .md is out of step with the fact"
        open(MD, "w", encoding="utf-8").write(md.replace(OLD, NEW))
        print(".md updated too")

    # only these three changed characters
    assert len(new) == len(text) - (len(OLD) - len(NEW)), "unexpected length change"
    print(f"\nfreeze-words left in the script: {new.count('unmoving')} 'unmoving'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
