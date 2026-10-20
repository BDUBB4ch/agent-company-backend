"""BARRY'S WEAPON-CARRY RULING, 2026-09-20. His words, verbatim:

  "their weapon should only be mentioned as their common build. in their
   holsters unless its being used. Tazz has a bug gun so hers should be on
   her back held my magnets or some sci fi shit"

Adds ONE new section to the canon, immediately after the COLOUR IS THE FASTEST
CHECK line in WHO CARRIES WHAT. It does NOT touch a single character anchor --
his descriptions are set and are not Claude's to edit.

Writes BOTH copies (fact 592 and data/barry-character-canon.md) and asserts
they are byte-identical after, because the documented failure mode of this
document is the two copies drifting.

Re-runnable: refuses to insert twice.
"""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "brain.db")
DISK = os.path.join(ROOT, "data", "barry-character-canon.md")
FACT_ID = 592

ANCHOR = ("COLOUR IS THE FASTEST CHECK. Purple = Bia. Green = Yannah. "
          "Pink = Tazz. If the\nglow in your prompt does not match the hand "
          "it is in, the prompt is wrong.\n")

MARKER = "HOW THEY CARRY IT -- STOWED IS THE DEFAULT"

BLOCK = """
===============================================================
HOW THEY CARRY IT -- STOWED IS THE DEFAULT
Barry, 2026-09-20, his words: "their weapon should only be mentioned as their
common build. in their holsters unless its being used. Tazz has a bug gun so
hers should be on her back held my magnets or some sci fi shit"
===============================================================

A weapon is part of the character's COMMON BUILD. It rides where it lives and
it stays there. Nobody stands around holding a gun. It comes out only on the
beat that actually uses it -- drawn, raised, fired, or being put away.

  Bia        energy revolver            LEFT HIP, holstered (silenced mode)
  Yannah     machine pistol             THIGH HOLSTER on her rig
  Tazz       two-handed missile weapon  ACROSS HER BACK on a magnetic mount.
             It is too big for a holster: it sits flush against her back and
             releases when she reaches for it. She rarely draws it at all --
             that habit is unchanged.
  B Dubb     all-black pistol           BELT, holstered
  Keth       carries nothing
  Vor'Shara  carries nothing

HOW TO WRITE IT: name the carry as part of the LOOK, in plain words --
"@Yannah's thigh holster", "@Tazz's blaster racked across her back on its
magnetic mount", "@b-dubb's pistol on his belt".

DO NOT USE THE WEAPON'S @HANDLE FOR A STOWED WEAPON. The handle BINDS the
weapon asset, and a bound hero-weapon asset gets drawn -- usually into the
character's hand -- whatever the prose says around it. Measured 2026-09-20:
"@Yannah's-Machine-Pistol at her thigh" still came back as a gun in her hand,
which is what Barry caught. The weapon handle goes in ONLY on the beat the
weapon is in use; stowed is wardrobe, and wardrobe is words.
"""


def main() -> int:
    conn = sqlite3.connect(DB)
    fact = conn.execute(
        "select content from facts where id=?", (FACT_ID,)).fetchone()
    if not fact:
        print(f"FAIL: fact {FACT_ID} not found")
        return 1
    fact_text = fact[0]
    disk_text = open(DISK, encoding="utf-8").read()

    if fact_text != disk_text:
        print("FAIL: the two canon copies already DIFFER -- diff and "
              "reconcile them before inserting anything.")
        print(f"      fact {len(fact_text)} vs disk {len(disk_text)}")
        return 1
    print(f"both copies identical at {len(fact_text)} chars")

    if MARKER in fact_text:
        print("already applied -- nothing to do")
        return 0

    if fact_text.count(ANCHOR) != 1:
        print(f"FAIL: anchor found {fact_text.count(ANCHOR)} times, expected 1")
        return 1

    updated = fact_text.replace(ANCHOR, ANCHOR + BLOCK, 1)

    # Backups BEFORE either write.
    stamp = "2026-09-20_weapon_carry"
    open(os.path.join(ROOT, "data", f"backup_fact592_canon_before_{stamp}.md"),
         "w", encoding="utf-8").write(fact_text)
    open(os.path.join(ROOT, "data", f"backup_disk_canon_before_{stamp}.md"),
         "w", encoding="utf-8").write(disk_text)

    conn.execute("update facts set content=? where id=?", (updated, FACT_ID))
    conn.commit()
    tmp = DISK + ".tmp"
    open(tmp, "w", encoding="utf-8", newline="").write(updated)
    os.replace(tmp, DISK)

    # Verify from the real sources, not from the variable.
    back_fact = conn.execute(
        "select content from facts where id=?", (FACT_ID,)).fetchone()[0]
    back_disk = open(DISK, encoding="utf-8").read()
    if back_fact != back_disk:
        print("FAIL: copies differ AFTER the write")
        return 1
    if MARKER not in back_fact:
        print("FAIL: block not present after the write")
        return 1
    # Nothing but the insert may have moved.
    if len(back_fact) != len(fact_text) + len(BLOCK):
        print(f"FAIL: unexpected size change {len(fact_text)} -> {len(back_fact)}")
        return 1

    print(f"applied: {len(fact_text)} -> {len(back_fact)} chars, both copies "
          f"byte-identical")
    print("character anchors untouched:",
          back_fact.count("@TAZZ: Alien woman") == 1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
