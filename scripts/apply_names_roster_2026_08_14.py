"""THE NAMES ROSTER -- Barry, 2026-08-14: "also put the names of the characters
and the locations in Elliots skills. it should just be part of how he writes for
this on my local and when giving me prompts for higgsfield."

The character and weapon handles were already in this document. The LOCATIONS
were not, anywhere. They are taken VERBATIM from the scene slugs in his own EP1
documents (ep1-production-script, ep1-wrong-box-script-CANON-v7,
ep1-scene-anchors) -- extracted, not invented, and not paraphrased.

Worth recording: @TALIA is HIS OWN handle. His script writes "INT. @TALIA --
CARGO HOLD -- CONTINUOUS". An earlier note today claiming Elliot invented it was
wrong; he took it from the script, which is exactly what he should do.

Re-runnable: keyed on MARKER.
"""
import pathlib
import sqlite3

MARKER = "THE NAMES ROSTER -- USE THESE NAMES, NOT YOUR OWN"

ROSTER = '''
===============================================================
THE NAMES ROSTER -- USE THESE NAMES, NOT YOUR OWN
Barry, 2026-08-14: the names are "just part of how he writes" -- for local
renders and for the Higgsfield prompts he pastes. Never substitute a
description for a name that exists, and never make up a name that does not.
===============================================================

CHARACTERS -- handles, and they work in BOTH destinations (local @mention loads
his trained LoRA; Higgsfield resolves the trained asset):
  @Bia-2   @Yannah   @Tazz   @B-DUBB-new   @Keth   @Vorshara

WEAPONS -- HIGGSFIELD ONLY. Nothing is trained on them locally, so in a local
```image``` fence write the gun in plain words instead:
  @Bia's-Pistol*             -> locally: "her energy revolver"
  @Yannah's-Machine-Pistol   -> locally: "her liquid-metal machine pistol"
  @Tazz's-Weapon             -> locally: "her two-handed missile blaster"
  B Dubb's Glock .40 has no handle anywhere -- always words.

LOCATIONS -- lifted verbatim from the scene slugs in Barry's own EP1 scripts.
Use HIS name for a place; do not rename it, do not "improve" it, and do not
invent a new one. @TALIA is the one that carries an @ in his own writing
("INT. @TALIA -- CARGO HOLD -- CONTINUOUS"), and he @s a character's room the
same way ("@TAZZ'S QUARTERS"). No other location carries an @ in his scripts,
so do not add one.

  THE SHIP -- @TALIA
    @TALIA -- CARGO HOLD          (the most-used location in EP1)
    @TALIA -- COMMON AREA
    @TALIA -- BRIDGE
    @TALIA -- MAIN CORRIDOR
    @TALIA -- VARIOUS CORRIDORS
    @TALIA -- CORRIDOR VIEWPORT
    @TALIA -- SPARE QUARTERS
    @TALIA -- @TAZZ'S QUARTERS
    EXT. @TALIA -- DEEP SPACE

  THE BLACK SITE (Earth, the EP1 raid)
    BLACK SITE -- SHIPPING BAY
    BLACK SITE -- WAREHOUSE MAIN FLOOR
    BLACK SITE -- WAREHOUSE SIDE ROOM
    BLACK SITE -- SERVICE CORRIDOR
    BLACK SITE -- LABORATORY CORRIDOR
    BLACK SITE -- SECURED LAB ROOM  (and SECURED LAB ROOM DOOR)
    EXT. BLACK SITE -- PERIMETER / INTERIOR PERIMETER / NORTHEAST CORNER
    EXT. BLACK SITE -- WIDE FROM TREE LINE

  OUTSIDE (Colorado)
    EXT. ROCKY MOUNTAINS -- COLORADO -- NIGHT
    EXT. ROCKY MOUNTAINS -- DENSE PINE FOREST
    EXT. ROCKY MOUNTAINS -- STEEP ROCKY SLOPE
    EXT. RIDGE LINE -- COLORADO
    EXT. TREE LINE -- TIGHT PERIMETER
    EXT. WOODS

  THE BOX ITSELF
    INT. MATTE-BLACK CRATE  (also written BLACK CRATE -- darkness inside)

HOW THIS SHOWS UP IN THE WRITING: name the character, name the weapon, name the
place, THEN direct the shot. A prompt that says "a cargo hold" when the script
says @TALIA -- CARGO HOLD has thrown away the one thing that keeps the series
looking like one series.
'''

REPO = pathlib.Path(__file__).resolve().parent.parent
ANCHOR = "WHICH PROMPT GETS HANDLES -- THE TWO DESTINATIONS ARE NOT THE SAME"


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

    out = text.replace(ANCHOR, ROSTER.strip("\n") + "\n\n" + ANCHOR, 1)
    disk.write_text(out, encoding="utf-8")
    conn.execute("UPDATE facts SET content = ? WHERE id = 592", (out,))
    conn.commit()
    conn.close()
    print(f"canon {len(text):,} -> {len(out):,} chars ({len(out) - len(text):+,}), both copies")


if __name__ == "__main__":
    main()
