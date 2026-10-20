"""Tightening pass on the weapon-pairing rule -- 2026-08-14.

Trap test after the first pass: fed Elliot "Tazz snaps up her PISTOL one-handed,
B Dubb sprays his ALIEN RIFLE, GREEN plasma balls from Bia."
  * B Dubb -> corrected to the Glock .40 with brass. PASS.
  * Bia     -> corrected to violet plasma orbs from her revolver. PASS.
  * Tazz    -> named the right weapon but still wrote her ONE-HANDING it. FAIL.
He also corrected silently, which hides the fix from Barry.

So two gaps: handling is not covered by naming the weapon, and a correction has
to be said out loud. Both are now explicit.

Re-runnable: keyed on MARKER. Asserts its anchor before writing.
"""
import pathlib
import sqlite3

MARKER = "HOW IT IS HELD IS PART OF THE WEAPON"

RULE = '''
HOW IT IS HELD IS PART OF THE WEAPON, NOT A DETAIL YOU CAN BEND
Naming the right gun is only half of it. Measured failure, 2026-08-14: given a
brief that said "Tazz snaps up her pistol one-handed", Elliot correctly swapped
in the missile blaster and then still wrote her ONE-HANDING it.
  TAZZ    TWO HANDS, ALWAYS. Pistol grip and front foregrip, shouldered or
          braced. She never one-hands it, never fast-draws it, never twirls it.
          If a brief asks for that, it is asking for the old scatter-pistol.
  YANNAH  Two hands when she is pouring full-auto; one hand is fine at rest.
  BIA     One hand or two. Revolver, deliberate, one shot at a time -- never
          written as spraying.
  B DUBB  Earth handgun handling. Ordinary flash, brass ejecting.

IF A BRIEF GIVES SOMEONE THE WRONG WEAPON OR THE WRONG HANDLING, FIX IT AND SAY
SO IN ONE LINE. "Wrote Tazz two-handed -- her weapon is the two-handed missile
blaster, not a pistol." Do not fix it silently: Barry cannot correct canon he
never sees you changing, and he is the one who decides.
'''

REPO = pathlib.Path(__file__).resolve().parent.parent
ANCHOR = ("WHEN MORE THAN ONE OF THEM IS IN FRAME, name each character's weapon on the same\n"
          "line as that character")


def main() -> None:
    disk = REPO / "data" / "barry-character-canon.md"
    conn = sqlite3.connect(REPO / "data" / "brain.db")
    fact = conn.execute("SELECT content FROM facts WHERE id = 592").fetchone()[0]
    text = disk.read_text(encoding="utf-8")

    if text != fact:
        raise SystemExit("disk canon and fact 592 have DRIFTED -- fix that first.")
    if MARKER in text:
        print("already applied")
        return
    if text.count(ANCHOR) != 1:
        raise SystemExit(f"anchor missing/not unique ({text.count(ANCHOR)}x) -- nothing written.")

    out = text.replace(ANCHOR, RULE.strip("\n") + "\n\n" + ANCHOR, 1)
    disk.write_text(out, encoding="utf-8")
    conn.execute("UPDATE facts SET content = ? WHERE id = 592", (out,))
    conn.commit()
    conn.close()
    print(f"canon {len(text):,} -> {len(out):,} chars ({len(out) - len(text):+,}), both copies")


if __name__ == "__main__":
    main()
