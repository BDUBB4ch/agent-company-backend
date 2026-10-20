"""Keth's eyes are DARK GREEN -- Barry, 2026-08-08: "mka esure those eyes are
dark green" (i.e. "make sure those eyes are dark green").

Refines the same-day anchor wording "Large GREEN eyes" to DARK GREEN. Applied
to BOTH copies of the canon, which is the thing that drifted before:
  - data/barry-character-canon.md on disk
  - facts.id=592 (knowledge:talia_crew, source_name barry-character-canon.md),
    the copy all 9 agents read and Elliot pins

Not written into any training caption -- captions in lora_keth_v5 are
deliberately minimal, and spec-in-caption was bug 3 of the 2026-08-08
post-mortem. This governs PROMPTING and judging renders.

Run:  venv/Scripts/python.exe scripts/set_keth_eyes_dark_green.py
Idempotent: exits cleanly if the wording is already DARK GREEN.
"""
import os
import sqlite3

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(REPO, "data", "brain.db")
DISK = os.path.join(REPO, "data", "barry-character-canon.md")
FACT_ID = 592

OLD_LINE = "hair. Large GREEN eyes -- green iris with a dark pupil, no visible white /\nno sclera."
NEW_LINE = "hair. Large DARK GREEN eyes -- DARK GREEN iris with a dark pupil, no\nvisible white / no sclera."

OLD_NOTE = '''green, just like the new images" -- so GREEN, matching that ruling, and'''
NEW_NOTE = '''green, just like the new images" -- so GREEN, and refined later the same
   day to DARK GREEN in his words: "make sure those eyes are dark green".
   This matches the 2026-08-04 ruling, and'''


def patch(doc: str) -> tuple:
    changed = 0
    if OLD_LINE in doc:
        doc = doc.replace(OLD_LINE, NEW_LINE, 1)
        changed += 1
    if OLD_NOTE in doc:
        doc = doc.replace(OLD_NOTE, NEW_NOTE, 1)
        changed += 1
    return doc, changed


def main() -> None:
    conn = sqlite3.connect(DB)
    live = conn.execute("SELECT content FROM facts WHERE id = ?", (FACT_ID,)).fetchone()
    if live is None:
        raise SystemExit(f"fact {FACT_ID} not found")
    live = live[0]

    if "DARK GREEN eyes" in live and "DARK GREEN eyes" in open(DISK, encoding="utf-8").read():
        print("already applied - nothing to do")
        return

    new_fact, n1 = patch(live)
    new_disk, n2 = patch(open(DISK, encoding="utf-8").read())
    if not n1 or not n2:
        raise SystemExit(f"refusing to guess: anchor wording not found (fact {n1}/2, disk {n2}/2)")

    with open(DISK, "w", encoding="utf-8") as fh:
        fh.write(new_disk)
    conn.execute("UPDATE facts SET content = ? WHERE id = ?", (new_fact, FACT_ID))
    conn.commit()
    print(f"fact {FACT_ID}: {len(new_fact):,} chars   disk: {len(new_disk):,} chars   both patched")


if __name__ == "__main__":
    main()
