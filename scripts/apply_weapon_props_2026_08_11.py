"""PROPS -- WEAPONS. Barry, 2026-08-11. His words, verbatim.

Three prop/product reference prompts, one per character sidearm. Saved to BOTH
canon copies (disk + facts.id=592) so all 9 agents have them.

Written as a script file, never through bash -c python -c -- quotes and shell
metacharacters have silently eaten fact text before.
"""
import pathlib
import sqlite3

SPEC = '''

===============================================================
PROPS -- WEAPONS. BARRY, 2026-08-11. HIS WORDS, VERBATIM.
Prop/product reference shots (single weapon, pure white background). Each has a
"firing variant" line to add when you want the muzzle effect shown.
These are the detailed spec for the "alien pistol" each character already carries
in her anchor -- they fill that line in, they do not replace it.
===============================================================

--- BIA'S REVOLVER ---
Hyper-realistic, photorealistic prop/product shot of Bia's sidearm - a sleek futuristic
revolver clearly based on an Earth .357 Magnum (six-shot revolver silhouette: fluted
cylinder, top strap, exposed hammer, contoured grip) but forged from a strange otherworldly
metal that is mostly a deep matte dark alloy, with a shifting iridescent, pearlescent,
oil-slick sheen catching only on the edges, curves, and high points. Functional glow, not
decorative: soft violet/purple luminescence concentrated at the cylinder gaps and a small
energy/charge readout indicator near the hammer, the rest of the frame dark so the glow reads
with contrast. Real working controls - trigger inside a properly sized trigger guard, knurled
cylinder-release latch, real ejector rod, and a checkered/textured grip molded for a human
hand. Strong matte-vs-gloss material contrast; faint honest wear on the edges, muzzle, and
grip corners; a fingerprint smudge near the grip. Refined, exotic, deadly. Single weapon
centered, 3/4 hero angle showing the full profile, resting on a clean surface, pure white
background, even studio lighting, ultra-high detail, razor-sharp focus, no hands, no text or
logos, 16:9.
FIRING VARIANT: add - "...caught mid-fire: a beautiful vivid purple muzzle flash bursting
from the barrel with a thin curl of smoke rising from the muzzle."

--- YANNAH'S MACHINE PISTOL ---
Hyper-realistic, photorealistic prop/product shot of Yannah's custom machine pistol - a
squared, boxy frame with the blocky Glock-like silhouette, visibly hand-built and expertly
upgraded by a brilliant engineer: cleanly integrated tech, precision panel lines, cooling
vents, an extended machine-pistol magazine, a stubby compensator/suppressor at the muzzle, a
charging handle, and a select-fire switch (full-auto build, fast and accurate like an Uzi).
Maker's tells that show she built it herself - one slightly mismatched panel, a couple of
visible hex fasteners, a hand-wrapped grip, and a sliver of neatly routed wiring under a small
clear inspection panel. Mounted on the top rail is a small compact holographic sight
projecting a glowing floating targeting reticle just above the slide, its light spilling
faintly back onto the top of the slide. Real working controls - trigger and trigger guard,
magazine release, textured grip. Matte-vs-gloss material contrast (matte frame, satin metal,
one glowing tech accent); faint honest wear on edges and contact points. Purposeful,
high-quality, refined-homemade craftsmanship. Single weapon centered, 3/4 hero angle, pure
white background, even studio lighting, ultra-high detail, sharp focus, no hands, no text or
logos, 16:9.
FIRING VARIANT: add - "...firing: muzzle flash almost invisible, just faint soft sparks
flickering at the barrel."

--- TAZZ'S SCATTER PISTOL ---
Hyper-realistic, photorealistic prop/product shot of Tazz's scatter-pistol - a cool, striking
futuristic handgun with the flowing lines of a Ruger, refined and sci-fi. Matte black body and
slide with polished chrome accents - a chrome trigger, chrome hammer and controls, and a
chrome muzzle ring - plus glowing hot-pink piping: thin pink accent light-lines running along
the frame seams and down the slide. The muzzle is a wide cluster of nine tiny micro-missile
launch tubes arranged in a honeycomb ring (it fires nine tiny guided missiles at once, like a
buckshot spread), with tiny missile tips visible seated inside the tubes and a chunky front
end housing the launch cluster; magazine sized for 14 shots. Textured grip panel molded for a
real hand, visible trigger guard, magazine release, and loading breech; strong matte-vs-gloss
material contrast (matte black polymer, satin chrome metal, glossy pink glow); faint honest
edge wear on the corners and muzzle. Single weapon centered, 3/4 hero angle showing the full
profile with soft studio reflections playing across the chrome, pure white background, even
studio lighting, ultra-high detail, sharp focus, no hands, no text or logos, 16:9.
FIRING VARIANT: add - "...firing: nine tiny corkscrewing micro-missiles spiraling out of the
muzzle cluster, each leaving a twisting pinkish smoke trail."

QUICK REFERENCE -- which gun is whose, and its signature:
  BIA     revolver, .357-Magnum silhouette, dark iridescent alloy, VIOLET/PURPLE glow at the
          cylinder gaps. Purple muzzle flash when firing.
  YANNAH  boxy Glock-like machine pistol, hand-built by her, holographic sight with a floating
          reticle, suppressor/compensator, full-auto. Almost no muzzle flash - faint sparks.
  TAZZ    Ruger-lined scatter-pistol, matte black + chrome, HOT-PINK piping, nine-tube
          honeycomb micro-missile muzzle, 14-shot magazine. Nine corkscrewing missiles when
          firing.

NOTE ON GENERATING THESE LOCALLY: these are text-only prop shots with no character in them,
so they do NOT go through the Kontext reference pipeline (Kontext needs a reference image and
governs identity from it). Render props on the SDXL checkpoint instead. The "pure white
background, no hands, no text or logos" wording is already in his prompts -- keep it.
'''

REPO = pathlib.Path(__file__).resolve().parent.parent
MARKER = "PROPS -- WEAPONS. BARRY, 2026-08-11"


def main() -> None:
    disk = REPO / "data" / "barry-character-canon.md"
    s = disk.read_text(encoding="utf-8")
    if MARKER not in s:
        disk.write_text(s + SPEC, encoding="utf-8")
        print(f"disk canon -> {len(s + SPEC):,} chars")
    else:
        print("disk canon: already applied")

    conn = sqlite3.connect(REPO / "data" / "brain.db")
    t = conn.execute("SELECT content FROM facts WHERE id = 592").fetchone()[0]
    if MARKER not in t:
        conn.execute("UPDATE facts SET content = ? WHERE id = 592", (t + SPEC,))
        conn.commit()
        print(f"fact 592   -> {len(t + SPEC):,} chars")
    else:
        print("fact 592: already applied")


if __name__ == "__main__":
    main()
