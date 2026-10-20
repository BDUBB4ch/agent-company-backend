"""ASSET NAMES FOR PROMPTS -- Barry, 2026-08-14.

He gave the new asset handles for his characters and their weapons, plus three
zips of NEW weapon reference renders. This writes the names into BOTH canon
copies (disk + facts.id=592) so every agent -- and Elliot in particular, who
has barry-character-canon PINNED in full -- reads them on every message.

Re-runnable: keyed on MARKER, so a second run is a no-op. Written as a script
file, never through bash -c python -c: quotes and backticks have silently
eaten fact text before.
"""
import pathlib
import sqlite3

SPEC = '''

===============================================================
ASSET NAMES FOR PROMPTS -- BARRY, 2026-08-14.
His instruction, verbatim: "these are the new names for my prompts, for my
characters and their weapons." These are the strings to TYPE in a prompt.
Where a name below differs from the older @mention list in this document,
THIS SECTION WINS.
===============================================================

CHARACTERS
  @Bia-2                    Bia          (use instead of @Bia)
  @Yannah                   Yannah       (unchanged)
  @B-DUBB-new               B Dubb       (use instead of @BDUBB)
  @Tazz                     Tazz         (unchanged)

WEAPONS -- the guns are assets now too, and get named the same way
  @Bia's-Pistol*            Bia's revolver
  @Yannah's-Machine-Pistol  Yannah's machine pistol
  @Tazz's-Weapon            Tazz's missile-cluster weapon

NOT RENAMED, so do not change them: @Keth and @Vorshara. B Dubb's Glock .40 is
an ordinary Earth handgun with no asset -- spell that one out in words.

HOW TO USE THEM
* Type the handle EXACTLY as written above -- hyphens, apostrophe, capitals as
  shown, and the trailing * on Bia's pistol. These are asset handles, not
  English: "Bia's Pistol" is a different string from "@Bia's-Pistol*" and will
  not resolve.
* Order in the prompt: character handle FIRST, then her weapon handle, then the
  look from THIS document, then the scene.
* Name the weapon by its handle INSTEAD OF describing the gun. Describing it in
  words on top of the handle is how a prompt ends up fighting itself -- the same
  failure as re-describing a face that a character asset already carries.
* Still true: one character per render is strongest, two work with the first
  getting the truest likeness, three or more blend and fail. Trained likenesses
  apply to IMAGES -- for VIDEO, spell the look out in full words.

THE NEW WEAPON REFERENCE RENDERS (Barry supplied 2026-08-14; the reference
governs, so this is what the guns now look like). Files live in
data/props/<weapon>/, hero frames staged for local work at
tools/ComfyUI/input/bia_pistol_ref.png, yannah_pistol_ref.png,
tazz_weapon_ref.png.

  BIA'S PISTOL -- matches her written prop prompt. Revolver on a .357 Magnum
  silhouette, dark alloy with a purple/blue-green iridescent oil-slick sheen,
  exposed hammer, checkered rubber grip, fluted vented muzzle. Violet plasma
  visibly crackling inside the cylinder chambers, a glowing violet energy tube
  running along the top of the barrel back into the cylinder, and a lit
  "REFILLS: 8" readout with a segmented charge bar on the frame beside the
  cylinder. FIRING: a bright violet plasma orb leaving the muzzle, gold sparks,
  a curl of smoke -- and the readout counts down (8 -> 7).

  YANNAH'S MACHINE PISTOL -- the reference does NOT match her 2026-08-11
  written prompt, and the difference is the whole look of the gun. Reference:
  boxy machine pistol in scuffed off-white/bone ceramic-look panels (not matte
  black), a transparent cylindrical magazine of glowing green fluid seated in
  the grip, a green light channel routed along the top of the slide, a compact
  holographic sight projecting a green reticle, hand-wrapped grip tape, top
  rail, small clear inspection window over the internals. FIRING: no muzzle
  flash -- teardrop-shaped metallic green projectiles leaving the muzzle on
  green trails with pale smoke. What carried over: boxy silhouette, hand-built
  wear and maker's tells, holographic sight, near-flashless firing.
  ** OPEN FOR BARRY: does the new reference replace the written prompt? **

  TAZZ'S WEAPON -- her signature carried over, the class of weapon did not. It
  is no longer a pistol: it is a compact PDW/SMG with a folding skeleton stock,
  full-length top picatinny rail, slotted M-LOK handguard, angled foregrip with
  chrome marbled panels, and a transparent drum magazine of pink-tipped rounds
  under the receiver. Kept: matte black body, hot-pink glowing light piping
  along the handguard and receiver, chrome honeycomb muzzle shroud over a
  nine-tube micro-missile cluster with pink-tipped missiles seated in the tubes.
  FIRING: nine pink-tipped micro-missiles corkscrewing out on twisting pink
  smoke trails.
  ** OPEN FOR BARRY: "scatter-pistol" in her written prompt vs the SMG in the
  reference -- which is the gun? **

The 2026-08-11 written prop prompts stay in this document below. Nothing is
deleted; where they and the new references disagree, the two items flagged
above are Barry's call, not ours.
'''

REPO = pathlib.Path(__file__).resolve().parent.parent
MARKER = "ASSET NAMES FOR PROMPTS -- BARRY, 2026-08-14"


def main() -> None:
    disk = REPO / "data" / "barry-character-canon.md"
    s = disk.read_text(encoding="utf-8")
    if MARKER not in s:
        disk.write_text(s + SPEC, encoding="utf-8")
        print(f"disk canon -> {len(s + SPEC):,} chars (+{len(SPEC):,})")
    else:
        print("disk canon: already applied")

    conn = sqlite3.connect(REPO / "data" / "brain.db")
    t = conn.execute("SELECT content FROM facts WHERE id = 592").fetchone()[0]
    if MARKER not in t:
        conn.execute("UPDATE facts SET content = ? WHERE id = 592", (t + SPEC,))
        conn.commit()
        print(f"fact 592   -> {len(t + SPEC):,} chars (+{len(SPEC):,})")
    else:
        print("fact 592: already applied")
    conn.close()


if __name__ == "__main__":
    main()
