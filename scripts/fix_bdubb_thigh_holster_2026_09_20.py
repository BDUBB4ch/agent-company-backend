"""B DUBB CARRIES ON A THIGH HOLSTER. Barry, 2026-09-20: "b dubb has a thigh
holster."

Corrects the one line Claude got wrong in the HOW THEY CARRY IT section added
earlier the same night -- it said "BELT, holstered", read off his anchor's
"Belt: all-black pistol ... utility knife in sheath, tactical gloves tucked at
hip" line.

HIS ANCHOR IS NOT EDITED. His newest word governs the PISTOL's placement; the
knife and the gloves stay on the belt exactly as his anchor lists them, and
the anchor keeps its own wording on record. Both canon copies, byte-identical
after, backups first. Re-runnable.
"""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "brain.db")
DISK = os.path.join(ROOT, "data", "barry-character-canon.md")
FACT_ID = 592

OLD = "  B Dubb     all-black pistol           BELT, holstered\n"
NEW = ("  B Dubb     all-black pistol           THIGH HOLSTER\n"
       "             (Barry, 2026-09-20: \"b dubb has a thigh holster.\" His\n"
       "              anchor's \"Belt:\" line lists the pistol with the utility\n"
       "              knife and the tactical gloves -- the KNIFE AND GLOVES\n"
       "              stay on the belt; the PISTOL rides a thigh holster.\n"
       "              Newest word governs. The anchor keeps its own wording.)\n")


def main() -> int:
    conn = sqlite3.connect(DB)
    fact = conn.execute(
        "select content from facts where id=?", (FACT_ID,)).fetchone()[0]
    disk = open(DISK, encoding="utf-8").read()
    if fact != disk:
        print(f"FAIL: copies differ ({len(fact)} vs {len(disk)}) -- reconcile first")
        return 1
    if "B Dubb     all-black pistol           THIGH HOLSTER" in fact:
        print("already applied")
        return 0
    if fact.count(OLD) != 1:
        print(f"FAIL: target line found {fact.count(OLD)} times, expected 1")
        return 1

    stamp = "2026-09-20_bdubb_thigh"
    open(os.path.join(ROOT, "data", f"backup_fact592_canon_before_{stamp}.md"),
         "w", encoding="utf-8").write(fact)
    open(os.path.join(ROOT, "data", f"backup_disk_canon_before_{stamp}.md"),
         "w", encoding="utf-8").write(disk)

    updated = fact.replace(OLD, NEW, 1)
    conn.execute("update facts set content=? where id=?", (updated, FACT_ID))
    conn.commit()
    tmp = DISK + ".tmp"
    open(tmp, "w", encoding="utf-8", newline="").write(updated)
    os.replace(tmp, DISK)

    back_fact = conn.execute(
        "select content from facts where id=?", (FACT_ID,)).fetchone()[0]
    back_disk = open(DISK, encoding="utf-8").read()
    if back_fact != back_disk:
        print("FAIL: copies differ AFTER the write")
        return 1
    # His anchor must be exactly as it was.
    if back_fact.count("Belt: all-black pistol --") != 1:
        print("FAIL: his anchor's Belt line moved -- it must not")
        return 1
    print(f"applied: {len(fact)} -> {len(back_fact)} chars, both copies "
          f"byte-identical, anchor untouched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
