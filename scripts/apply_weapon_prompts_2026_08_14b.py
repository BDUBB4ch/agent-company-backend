"""BARRY'S FULL WEAPON PROMPTS -- his words, verbatim, 2026-08-14 (second pass).

He supplied complete A (Regular State) / B (Firing State) prompts for all three
guns, plus the lore behind them (energy cartridges, flash-frozen liquid metal,
caseless micro-missiles) and one correction: "exept I created a white variation
for Yannah" -- so the white gun is a VARIATION of a forest-green weapon, not the
base look.

This rebuilds the whole PROPS section:
  * His three verbatim prompts become the CURRENT spec.
  * Claude's reverse-engineered "CURRENT" blocks from earlier today are DELETED
    -- they were my prose describing his renders, and his own spec now exists.
    Deleting my words is fine; his are never deleted.
  * His 2026-08-11 prompts stay below, marked SUPERSEDED -- his words, kept.

Punctuation only is normalised to ASCII (em dash -> --, curly quotes -> plain)
to match the rest of this file. No word is changed, added or reordered.

Applies to BOTH canon copies, which are verified byte-identical first.
Re-runnable: keyed on MARKER.
"""
import pathlib
import sqlite3

MARKER = "PROPS -- WEAPONS. BARRY'S FULL PROMPTS, 2026-08-14"

NEW_SECTION = '''===============================================================
PROPS -- WEAPONS. BARRY'S FULL PROMPTS, 2026-08-14. HIS WORDS, VERBATIM.
Each weapon has TWO prompts: A. Regular State (at rest) and B. Firing State.
Use them as written. These SUPERSEDE the 2026-08-11 prompts, which are kept
further down for the record and must not be rendered from.
Only punctuation was normalised to ASCII; no wording was changed.
Reference renders he supplied the same day: data/props/{bia-pistol,
yannah-machine-pistol,tazz-weapon}/, hero frames staged for local work at
tools/ComfyUI/input/{bia_pistol,yannah_pistol,tazz_weapon}_ref.png.
===============================================================

BIA'S ENERGY REVOLVER -- signature: purple w/ white-hot core

A. Regular State
Hyper-realistic, photorealistic prop/product shot of Bia's sidearm at rest, not firing - a
sleek futuristic double-action ENERGY revolver that fires plasma balls one at a time like a
real .357 Magnum - but unmistakably an ALIEN weapon from the year ~3482, not Earth-made:
sculpted flowing lines, a seamless exotic-alloy shell with no visible screws or crude
machining, glowing violet energy conduits threading through the frame from the cartridge to
the emitter, and an emitter shroud in place of a plain barrel (still clearly a revolver in
silhouette). Mechanically believable: a six-chamber rotating cylinder (closed) that reads as a
segmented glowing energy core rather than plain steel, with six glowing plasma-charged
chambers, powered by a replaceable energy cartridge that slots into the base of the cylinder /
grip; the cartridge auto-refills the six chambers up to nine times before it's spent, then she
swaps a fresh cartridge (roughly 54 plasma shots per cartridge). A spring-loaded cartridge
release, a thumb cylinder-release latch, a working exposed hammer/striker and firing contact, a
real trigger inside a properly sized trigger guard, and a rifled-look plasma emitter at the
muzzle. Forged from a strange otherworldly metal that is mostly a deep matte dark alloy, with a
shifting iridescent, pearlescent, oil-slick sheen catching only on the edges, curves, and high
points. Functional glow: violet/purple luminescence with hints of white-hot at the cylinder
chambers plus a small charge/ammo readout near the hammer showing remaining refills, the rest
of the frame dark so the glow reads with contrast. Checkered/textured grip molded for a human
hand. Strong matte-vs-gloss material contrast; faint honest wear on the edges, muzzle, and grip
corners. Single weapon centered, 3/4 hero angle showing the full profile, resting on a clean
surface, pure white background, even studio lighting, ultra-high detail, razor-sharp focus, no
hands, no text or logos, 16:9.

B. Firing State
Hyper-realistic, photorealistic action shot of Bia's energy revolver firing a single plasma
ball - the same sleek futuristic alien double-action revolver of deep matte otherworldly alloy
with iridescent edges, glowing violet energy conduits, six-chamber energy-core cylinder, energy
cartridge seated, exposed hammer/striker dropped, charge readout lit, real trigger and textured
grip. Caught mid-shot: a vivid purple plasma ball with a bright white-hot core launching from
the emitter, yellow sparks kicking off the muzzle and a thin curl of vapor, purple-and-white
light spilling onto the frame (fires with a deep .357-style boom). Weapon locked level as if
just fired, single weapon centered, 3/4 hero angle, pure white background, even studio
lighting, ultra-high detail, sharp focus, no hands, no text or logos, 16:9.


YANNAH'S LIQUID-METAL MACHINE PISTOL -- signature: forest green

*** THE WHITE GUN IS A VARIATION, NOT THE BASE. Barry, 2026-08-14: "exept I created a white
variation for Yannah." The prompt below is the weapon as he wrote it, forest green. The
white-panelled gun in data/props/yannah-machine-pistol/ (the one he said he likes) is HIS
variation of this same weapon -- same mechanism, same forest-green energy and rounds, white
shell. Both are hers; say which one you mean when you write a shot. ***

A. Regular State
Hyper-realistic, photorealistic prop/product shot of Yannah's custom liquid-metal machine
pistol at rest, not firing - a squared, boxy frame with the blocky Glock-like silhouette,
visibly hand-built by a brilliant engineer from far-future ALIEN components (year ~3482 tech,
not an Earth firearm): a smooth sculpted alloy-and-ceramic shell, seamless panels with glowing
forest-green energy conduits threading along the frame, exotic mostly-fastenerless construction
with just a few of her own hand-fitted parts showing - still clearly a compact machine pistol
in silhouette. Mechanically believable as a real full-auto weapon that fires a specialized
liquid metal which, at the instant of firing, flash-freezes into rounds shaped like imperfect
water drops / raindrops - a rounded droplet body tapering to a slight sharp point (not
needle-thin), each round a slightly different shape (no two alike), with a bright white-hot
center glowing inside the forest-green metal, NOT conventional bullet shapes (able to punch
through thick metal). It feeds from a detachable sealed fluid canister / liquid-reservoir
magazine that seats up through the grip (clearly removable, with a clear window showing the
fluid inside - a shimmering liquid metal, a reflective mercury-like molten metallic fluid in
forest green with a chrome-ish sheen swirling and rippling in the canister - swapped out when
empty) and a magazine-release button; fine feed-lines and valves route the fluid to a small
curing/forming chamber behind the barrel where each round is shaped and frozen; a charging
handle primes it; a select-fire switch (fires fast and accurate like an Uzi). Small vapor vents
(the freezing gives off soft sparks, not a big flash - so no spent-brass ejection port).
Mounted on the top rail is a small compact holographic sight projecting a glowing floating
targeting reticle just above the slide, its light spilling faintly back onto the slide. Maker's
tells that show she built it herself - one slightly mismatched panel, a couple of visible hex
fasteners, a hand-wrapped grip, and a sliver of neatly routed wiring under a small clear
inspection panel. Real working controls - trigger and trigger guard, canister release, textured
grip. Matte-vs-gloss material contrast (matte frame, satin metal, one glowing tech accent,
clear canister of reflective mercury-like forest-green liquid metal); faint honest wear on
edges and contact points. Single weapon centered, 3/4 hero angle, pure white background, even
studio lighting, ultra-high detail, sharp focus, no hands, no text or logos, 16:9.

B. Firing State
Hyper-realistic, photorealistic action shot of Yannah's custom liquid-metal machine pistol
firing full-auto - the same squared, boxy hand-built alien machine pistol with the clear
canister of reflective mercury-like forest-green liquid metal in the grip, top-rail holographic
targeting reticle glowing above the slide, charging handle, matte frame with satin metal and a
glowing tech accent. Caught mid-burst: the muzzle itself stays near-invisible - just faint soft
sparks and a shimmer of freezing liquid at the emitter, no big flash, no brass - but a fast
stream of freshly flash-frozen liquid-metal rounds streaks downrange, each one shaped like an
imperfect water drop / raindrop (rounded body tapering to a slight sharp point, not
needle-thin), each round a slightly different shape (no two alike), with a bright white-hot
center glowing inside; the rounds glow a bright metallic forest green (about 430 nits,
tracer-like) as they travel, each drop lit in mid-air like a glowing tracer with a faint green
light trail, dark at the muzzle and brightening in flight; a light wisp of grey muzzle smoke
lingering at the barrel for a second or two after firing (not heavy). Weapon locked level as if
firing, single weapon centered, 3/4 hero angle, pure white background, even studio lighting,
ultra-high detail, sharp focus, no hands, no text or logos, 16:9.


TAZZ'S TWO-HANDED MISSILE WEAPON -- signature: hot pink
(the "mini missile blaster" of her anchor line -- same weapon, his name for it)

A. Regular State
Hyper-realistic, photorealistic prop/product shot of Tazz's weapon at rest, not firing - a
cool, striking futuristic TWO-HANDED weapon styled after a SIG MPX (boxy tactical SMG body, top
Picatinny rail, an M-LOK-style handguard up front for the support hand, and a compact folding
stock at the rear), with a roughly 6-inch barrel - but built as a far-future ALIEN weapon (year
~3482), not an Earth firearm: sculpted flowing lines over the MPX silhouette, exotic
alloy/ceramic panels, seamless construction with no crude screws, and glowing hot-pink energy
conduits threading along the body, rail, and drum (still clearly readable as a two-handed
missile carbine). Mechanically believable and fully caseless: a large SEE-THROUGH transparent
drum magazine mounted under the receiver holds a big stack of the loose tiny micro-missiles,
clearly visible through the clear drum; a feed system lifts nine missiles at a time up into the
nine-tube honeycomb muzzle cluster at the front (so nine tiny missile heads are always visible
seated in the tubes, ready to fire), and after each shot the next nine feed up from the drum to
reload the cluster. It fires all nine tiny guided micro-missiles at once (like a buckshot
spread). No cartridges, no shells, and no ejection port - the missiles themselves are the only
thing that leaves the gun, and the only exhaust is a vent of pink gas. A drum-release, a
charging handle, a real trigger and trigger guard, a textured pistol grip and a front
foregrip/handguard for the second hand. Matte black body with polished chrome accents - chrome
trigger, controls, and muzzle ring - plus glowing hot-pink piping running along the seams,
rail, and drum edge. Strong matte-vs-gloss material contrast (matte black polymer, satin
chrome, glossy pink glow, clear drum of visible missiles); faint honest wear on edges and
contact points. Single weapon centered, 3/4 hero angle showing the full profile with soft
studio reflections playing across the chrome, pure white background, even studio lighting,
ultra-high detail, sharp focus, no hands, no text or logos, 16:9.

B. Firing State
Hyper-realistic, photorealistic action shot of Tazz's two-handed MPX-style alien missile weapon
firing - the same matte-black-and-chrome futuristic weapon with hot-pink piping and glowing
conduits, chrome trigger, 6-inch barrel, folding stock deployed, nine-tube honeycomb muzzle
cluster, and see-through drum magazine (missile stack visible). Caught mid-shot: nine tiny
corkscrewing micro-missiles spiraling out of the muzzle cluster at once, each leaving a
twisting pinkish smoke trail - the missiles are caseless (no spent shells eject; the missiles
themselves are what leave the gun) - and a soft puff of glowing pink gas venting from the
barrel/muzzle as exhaust. Weapon locked level as if just fired, single weapon centered, 3/4
hero angle, pure white background, even studio lighting, ultra-high detail, sharp focus, no
hands, no text or logos, 16:9.


QUICK REFERENCE -- whose gun, what it does, and the lore that has to stay true:
  BIA     ENERGY REVOLVER, purple with a white-hot core. Alien-made (~3482) on a .357 Magnum
          silhouette. Fires ONE plasma ball at a time, deep .357-style boom. Six-chamber energy
          core; a replaceable cartridge auto-refills those six chambers up to NINE times
          (~54 shots) before she swaps it. Charge readout near the hammer shows refills left.
  YANNAH  LIQUID-METAL MACHINE PISTOL, forest green (WHITE VARIATION also hers). Full-auto,
          Uzi-fast. Fires liquid metal that FLASH-FREEZES at the muzzle into raindrop-shaped
          rounds - no two alike, white-hot centers, punch through thick metal, glow ~430 nits
          like tracers in flight. Sealed fluid canister through the grip; no brass, no ejection
          port, near-invisible muzzle flash, light grey smoke after.
  TAZZ    TWO-HANDED MISSILE WEAPON (her "mini missile blaster"), hot pink. SIG-MPX-styled
          carbine, ~6in barrel, folding stock, foregrip. FULLY CASELESS: a see-through drum
          feeds NINE micro-missiles at a time into a nine-tube honeycomb muzzle cluster, all
          nine fire at once like buckshot, next nine feed up. No shells, no ejection port - the
          only exhaust is a puff of pink gas. NOT a pistol.

WHAT THESE THREE HAVE IN COMMON, and why it matters when you write a shot: they are ALIEN
weapons from ~3482, not Earth guns with glow strips. Seamless sculpted shells, no crude screws,
energy conduits routed through the frame, and each one is fully believable mechanically - real
trigger, real guard, real release, real controls. None of the three ejects brass. Earth
silhouettes (.357, Glock, MPX) are the READABILITY anchor only.

NOTE ON GENERATING THESE LOCALLY: these are text-only prop shots with no character in them, so
they do NOT go through the Kontext reference pipeline (Kontext needs a reference image and
governs identity from it). Render props on the SDXL checkpoint instead. The "pure white
background, no hands, no text or logos" wording is already in his prompts -- keep it.


===============================================================
SUPERSEDED WEAPON PROMPTS -- BARRY'S 2026-08-11 WORDING. ON RECORD ONLY.
Kept because his words are never deleted. DO NOT RENDER FROM THESE -- every
one of them is replaced by the 2026-08-14 prompts above. Claude's own
reverse-engineered descriptions of the reference renders, written earlier on
2026-08-14, were deleted outright when his real prompts arrived.
===============================================================

--- SUPERSEDED: BIA'S REVOLVER (2026-08-11) ---
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

--- SUPERSEDED: YANNAH'S MACHINE PISTOL (2026-08-11) ---
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

--- SUPERSEDED: TAZZ'S SCATTER PISTOL (2026-08-11) ---
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


'''

# The asset-name section's reference notes were written before his real prompts
# arrived; two of them now under-describe the guns. Patch them rather than leave
# a stale read of the references sitting above his own spec.
PATCHES = [
    (
        "  ** RULED 2026-08-14 -- Barry: \"i like yannah's new white gun.\" The reference\n"
        "  is her gun. See her CURRENT spec in the PROPS section below. **",
        "  ** RULED 2026-08-14 -- Barry: \"i like yannah's new white gun\", then, giving the\n"
        "  full prompt: \"exept I created a white variation for Yannah.\" So the WHITE gun is\n"
        "  a variation he made of a FOREST-GREEN weapon. Both are hers. His full A/B prompt\n"
        "  in the PROPS section is the spec -- it also carries the mechanism the reference\n"
        "  cannot show you: it fires liquid metal that flash-freezes into raindrop rounds. **",
    ),
    (
        "  ** RULED 2026-08-14 -- Barry: \"change tazz's gun in lore to the mini missile\n"
        "  blaster.\" The reference is her weapon, it is no longer a pistol, and her\n"
        "  anchor line was updated to match. **",
        "  ** RULED 2026-08-14 -- Barry: \"change tazz's gun in lore to the mini missile\n"
        "  blaster.\" The reference is her weapon, it is no longer a pistol, and her anchor\n"
        "  line was updated to match. His full A/B prompt in the PROPS section is the spec:\n"
        "  a TWO-HANDED SIG-MPX-styled missile carbine, fully caseless, nine at a time. **",
    ),
]

REPO = pathlib.Path(__file__).resolve().parent.parent
SECTION_START = "===============================================================\nPROPS -- WEAPONS. BARRY, 2026-08-11"
SECTION_END = "===============================================================\nASSET NAMES FOR PROMPTS -- BARRY, 2026-08-14"


def rebuild(text: str) -> str:
    start = text.find(SECTION_START)
    end = text.find(SECTION_END)
    if start == -1 or end == -1 or end <= start:
        raise SystemExit("could not locate the props section boundaries -- nothing written.")
    out = text[:start] + NEW_SECTION + text[end:]
    for old, new in PATCHES:
        if out.count(old) != 1:
            raise SystemExit(f"patch anchor missing/not unique ({out.count(old)}x):\n{old[:80]}")
        out = out.replace(old, new)
    return out


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

    out = rebuild(text)
    disk.write_text(out, encoding="utf-8")
    conn.execute("UPDATE facts SET content = ? WHERE id = 592", (out,))
    conn.commit()
    conn.close()
    print(f"canon {len(text):,} -> {len(out):,} chars ({len(out) - len(text):+,}), both copies")


if __name__ == "__main__":
    main()
