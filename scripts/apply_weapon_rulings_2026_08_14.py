"""BARRY'S WEAPON RULINGS, 2026-08-14.

His words: "i like yannah's new white gun, and change tazz's gun in lore to the
mini missile blaster and yes the * is part of bias pistol"

So the two divergences flagged earlier today are settled in favour of the NEW
reference renders he supplied:
  * Yannah's machine pistol is the white/green gun.
  * Tazz's weapon is the mini missile blaster (the compact PDW-class launcher),
    not the "scatter-pistol" handgun in the 2026-08-11 wording.
  * The trailing * in @Bia's-Pistol* is part of the handle.

The 2026-08-11 wordings are NOT deleted -- house rule. They stay directly below
each current spec, relabelled SUPERSEDED so nothing reads them as live.

Applies to BOTH canon copies (disk + facts.id=592), which are byte-identical
and are checked as such before anything is written. Re-runnable: keyed on
MARKER. Every replacement asserts its anchor string exists, so a silent
partial edit is impossible.
"""
import pathlib
import sqlite3

MARKER = "RULED 2026-08-14"

# --- new current spec for Yannah, read off the references Barry supplied -----
YANNAH_NEW = '''--- YANNAH'S MACHINE PISTOL (CURRENT -- Barry's white gun, RULED 2026-08-14) ---
Hyper-realistic, photorealistic prop/product shot of Yannah's custom machine pistol - a
squared, boxy machine-pistol frame in scuffed off-white bone-coloured ceramic-composite
panels, visibly hand-built and expertly upgraded by a brilliant engineer. The power source
is a transparent cylindrical cell seated in the grip, filled with luminous swirling green
fluid that lights the hand holding it. Functional glow, not decorative: a thin green light
channel routed along the top of the receiver from the sight back into the body, and a small
clear inspection window over the internals showing neatly routed wiring. Mounted on the top
rail is a compact holographic sight projecting a glowing green targeting reticle above the
slide. Maker's tells that show she built it herself - a slightly mismatched panel, visible
hex fasteners, hand-wrapped grip tape, honest gray scuffs and smudge wear along the edges
and contact points. Real working controls - trigger inside a squared trigger guard, magazine
release, charging handle, select-fire switch (full-auto, fast and accurate like an Uzi),
front serrations, a short tube muzzle port. Strong matte-vs-gloss contrast: chalky matte
white panels, satin bare metal at the fasteners and muzzle, one glowing green tech accent.
Purposeful, high-quality, refined-homemade craftsmanship. Single weapon centered, 3/4 hero
angle, pure white background, even studio lighting, ultra-high detail, sharp focus, no hands,
no text or logos, 16:9.
FIRING VARIANT: add - "...firing: no muzzle flash at all - teardrop-shaped metallic green
projectiles streaking from the muzzle on bright green trails, with pale smoke curling behind."
REFERENCE: data/props/yannah-machine-pistol/ (2 renders), hero frame staged at
tools/ComfyUI/input/yannah_pistol_ref.png. The reference governs.

'''

# --- new current spec for Tazz --------------------------------------------
TAZZ_NEW = '''--- TAZZ'S MINI MISSILE BLASTER (CURRENT -- RULED 2026-08-14, replaces the scatter-pistol) ---
Hyper-realistic, photorealistic prop/product shot of Tazz's mini missile blaster - a compact
sci-fi PDW built on an Earth AR-pattern silhouette: folding skeleton stock, full-length top
picatinny rail, slotted M-LOK handguard, angled foregrip with polished chrome marbled side
panels, AR-style pistol grip, real trigger inside a proper trigger guard, safety selector and
charging controls. Matte black polymer and alloy body. Functional glow, not decorative:
glowing hot-pink light piping - one channel running the length of the top of the handguard,
a second along the receiver and barrel. The muzzle is a chrome honeycomb shroud over a cluster
of nine micro-missile launch tubes, pink-tipped missiles visible seated in the tubes (it fires
nine tiny guided missiles at once, like a buckshot spread). Feeding it is a transparent drum
magazine mounted under the receiver, pink-tipped rounds visible through the clear housing with
a pink glow ring around the drum face. Strong matte-vs-gloss contrast (matte black polymer,
satin chrome metal, glossy pink glow); faint honest edge wear on the corners and muzzle
shroud. Single weapon centered, 3/4 hero angle showing the full profile with soft studio
reflections playing across the chrome, pure white background, even studio lighting,
ultra-high detail, sharp focus, no hands, no text or logos, 16:9.
FIRING VARIANT: add - "...firing: nine pink-tipped micro-missiles corkscrewing out of the
muzzle cluster, each leaving a twisting pink smoke trail."
REFERENCE: data/props/tazz-weapon/ (6 renders), hero frame staged at
tools/ComfyUI/input/tazz_weapon_ref.png. The reference governs.
IN LORE she carries the mini missile blaster - Barry, 2026-08-14: "change tazz's gun in lore
to the mini missile blaster". It is NOT a pistol. Her anchor line was updated to match.

'''

REPLACEMENTS = [
    # 1. Tazz's anchor -- the weapon named in her verbatim anchor line.
    (
        "one-piece tactical jumpsuit -- SLEEVELESS. Alien pistol rarely drawn.",
        "one-piece tactical jumpsuit -- SLEEVELESS. Mini missile blaster (see PROPS)\n"
        "-- rarely drawn.\n"
        "  (Weapon changed by Barry 2026-08-14, his words: \"change tazz's gun in lore\n"
        "   to the mini missile blaster\". SUPERSEDED WORDING, kept on record: \"Alien\n"
        "   pistol rarely drawn.\" The rarely-drawn habit is unchanged -- only the gun.)",
    ),
    # 2. Yannah's current spec goes ABOVE the 2026-08-11 wording, which is relabelled.
    (
        "--- YANNAH'S MACHINE PISTOL ---",
        YANNAH_NEW
        + "--- YANNAH'S MACHINE PISTOL -- SUPERSEDED 2026-08-11 WORDING, DO NOT USE ---\n"
        "(Kept on record only. It describes a matte-black Glock-like gun; Barry ruled\n"
        "2026-08-14 that the white gun above is hers. Do not render from this block.)",
    ),
    # 3. Same for Tazz.
    (
        "--- TAZZ'S SCATTER PISTOL ---",
        TAZZ_NEW
        + "--- TAZZ'S SCATTER PISTOL -- SUPERSEDED 2026-08-11 WORDING, DO NOT USE ---\n"
        "(Kept on record only. It describes a Ruger-lined handgun; Barry ruled\n"
        "2026-08-14 that the mini missile blaster above is hers. Do not render\n"
        "from this block.)",
    ),
    # 4. Quick reference table -- the two changed entries.
    (
        "  YANNAH  boxy Glock-like machine pistol, hand-built by her, holographic sight with a floating\n"
        "          reticle, suppressor/compensator, full-auto. Almost no muzzle flash - faint sparks.\n"
        "  TAZZ    Ruger-lined scatter-pistol, matte black + chrome, HOT-PINK piping, nine-tube\n"
        "          honeycomb micro-missile muzzle, 14-shot magazine. Nine corkscrewing missiles when\n"
        "          firing.",
        "  YANNAH  boxy machine pistol, SCUFFED OFF-WHITE ceramic panels, GREEN glowing fluid cell in\n"
        "          the grip, green light channel, green holographic reticle, hand-built. Firing: no\n"
        "          flash - green teardrop projectiles on green trails.\n"
        "  TAZZ    MINI MISSILE BLASTER - compact AR-pattern PDW, folding stock, M-LOK handguard,\n"
        "          matte black + chrome, HOT-PINK piping, chrome honeycomb nine-tube micro-missile\n"
        "          muzzle, transparent drum magazine. Nine pink corkscrewing missiles when firing.\n"
        "          NOT a pistol - the scatter-pistol wording is superseded.",
    ),
    # 5. Close out the two questions flagged earlier today in the asset-name block.
    (
        "  ** OPEN FOR BARRY: does the new reference replace the written prompt? **",
        "  ** RULED 2026-08-14 -- Barry: \"i like yannah's new white gun.\" The reference\n"
        "  is her gun. See her CURRENT spec in the PROPS section below. **",
    ),
    (
        "  ** OPEN FOR BARRY: \"scatter-pistol\" in her written prompt vs the SMG in the\n"
        "  reference -- which is the gun? **",
        "  ** RULED 2026-08-14 -- Barry: \"change tazz's gun in lore to the mini missile\n"
        "  blaster.\" The reference is her weapon, it is no longer a pistol, and her\n"
        "  anchor line was updated to match. **",
    ),
    (
        "  shown, and the trailing * on Bia's pistol. These are asset handles, not",
        "  shown, and the trailing * on Bia's pistol -- Barry confirmed 2026-08-14,\n"
        "  \"yes the * is part of bias pistol\", so it is not a typo and must be typed.\n"
        "  These are asset handles, not",
    ),
    (
        "The 2026-08-11 written prop prompts stay in this document below. Nothing is\n"
        "deleted; where they and the new references disagree, the two items flagged\n"
        "above are Barry's call, not ours.",
        "Both open items were RULED by Barry the same day, in favour of the new\n"
        "references. The 2026-08-11 wordings for Yannah and Tazz are kept below their\n"
        "current specs, relabelled SUPERSEDED -- on record, never to be rendered from.\n"
        "Bia's 2026-08-11 prompt was already correct and is unchanged.",
    ),
]

REPO = pathlib.Path(__file__).resolve().parent.parent


def apply(text: str) -> str:
    for old, new in REPLACEMENTS:
        if old not in text:
            raise SystemExit(f"ANCHOR NOT FOUND, nothing written:\n{old[:90]}...")
        if text.count(old) != 1:
            raise SystemExit(f"ANCHOR NOT UNIQUE ({text.count(old)}x):\n{old[:90]}...")
        text = text.replace(old, new)
    return text


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

    out = apply(text)
    disk.write_text(out, encoding="utf-8")
    conn.execute("UPDATE facts SET content = ? WHERE id = 592", (out,))
    conn.commit()
    conn.close()
    print(f"canon {len(text):,} -> {len(out):,} chars (+{len(out) - len(text):,}), both copies")


if __name__ == "__main__":
    main()
