"""WHO CARRIES WHAT -- Barry, 2026-08-14: "make sure elliot knows how to write
the right weapons to the right character."

A hard character-to-weapon mapping written into the canon (disk + facts.id=592),
so it is in front of Elliot in full on every message rather than one read_skill
away. Names the three mix-ups that are actually likely, given what the old lore
used to say and what the guns look like.

Re-runnable: keyed on MARKER. Asserts its anchor before writing.
"""
import pathlib
import sqlite3

MARKER = "WHO CARRIES WHAT -- CHECK THIS BEFORE YOU WRITE A SHOT"

RULE = '''

===============================================================
WHO CARRIES WHAT -- CHECK THIS BEFORE YOU WRITE A SHOT
Barry, 2026-08-14: "make sure elliot knows how to write the right weapons to
the right character." Getting this wrong is not a style miss -- it is the
wrong character on screen.
===============================================================

  CHARACTER      HANDLE          WEAPON                      WEAPON HANDLE
  Bia            @Bia-2          energy revolver             @Bia's-Pistol*
                                 PURPLE plasma ball, white-hot core, one at a time
  Yannah         @Yannah         liquid-metal machine pistol @Yannah's-Machine-Pistol
                                 FOREST-GREEN raindrop rounds, full-auto (white variation
                                 is the same gun -- say which shell you mean)
  Tazz           @Tazz           two-handed missile weapon   @Tazz's-Weapon
                                 HOT-PINK, nine micro-missiles at once, two hands
  B Dubb         @B-DUBB-new     all-black Glock .40         -- no asset, write it in words
                                 Earth handgun. Muzzle flash and BRASS. No alien tech.
  Keth           @Keth           NONE. He is the pilot and does not carry.
  Vor'Shara      @Vorshara       NONE. She has guards; she does not hold a weapon.

COLOUR IS THE FASTEST CHECK. Purple = Bia. Green = Yannah. Pink = Tazz. If the
glow in your prompt does not match the hand it is in, the prompt is wrong.

THE THREE MIX-UPS TO WATCH FOR, because each one has a reason to happen:
1. TAZZ WITH A PISTOL. Her old lore called it a scatter-pistol and her anchor
   used to say "alien pistol". Both are superseded. Her weapon is TWO-HANDED --
   if you have written her one-handed, or drawing it fast, you have written the
   old gun. She also rarely draws it at all; that habit did not change.
2. B DUBB WITH AN ALIEN GUN. Three of the four carry ~3482 alien weapons and he
   does not. He is the Earth man in all-black tactical gear with a Glock .40, a
   utility knife and tactical gloves. His gun has an ordinary muzzle flash and
   ejects brass -- the alien three eject nothing at all.
3. BIA AND YANNAH SWAPPED. Both are hand-sized, both glow. Bia's is a REVOLVER
   that fires one plasma ball; Yannah's is a full-auto that streams raindrop
   rounds. Revolver + single purple ball = Bia. Stream of green drops = Yannah.

WHEN MORE THAN ONE OF THEM IS IN FRAME, name each character's weapon on the same
line as that character, never in a shared list at the end of the prompt. A pooled
list of guns is how a render ends up handing them to the wrong people.
'''

REPO = pathlib.Path(__file__).resolve().parent.parent
ANCHOR = "OLD HANDLES IN BARRY'S EXISTING SCRIPTS -- SUBSTITUTE, NEVER EDIT"


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

    # Sits immediately before the substitution rule, so the two prompt-writing
    # rules read together at the end of the asset-name block.
    out = text.replace(ANCHOR, RULE.strip("\n") + "\n\n" + ANCHOR, 1)
    disk.write_text(out, encoding="utf-8")
    conn.execute("UPDATE facts SET content = ? WHERE id = 592", (out,))
    conn.commit()
    conn.close()
    print(f"canon {len(text):,} -> {len(out):,} chars ({len(out) - len(text):+,}), both copies")


if __name__ == "__main__":
    main()
