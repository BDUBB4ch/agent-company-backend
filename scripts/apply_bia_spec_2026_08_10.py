"""Bia's expanded spec -- Barry, 2026-08-10, given while regenerating her on
Higgsfield. His words, appended to BOTH canon copies (disk + facts.id=592).

Written as a script file, never through bash -c python -c: backticks and quotes
get command-substituted and have silently blanked text out of a fact before.
"""
import pathlib
import sqlite3

SPEC = """

*** BIA -- EXPANDED SPEC. BARRY, 2026-08-10. HIS WORDS. ***
Given while regenerating her on Higgsfield.

Bia: Afro-Latina, age 26 but reads ~22, athletic curvy with natural proportions;
'cute baddy' / Lara Croft thirst-trap vibe but non-explicit; capable and unaware of
her sexiness; confident matter-of-fact slight bravado/military-type confidence.

VISUAL CANON:
  - subtly pointed ears
  - consistent hazel-green eyes with double-ring + subtle fractal iris pattern and
    faint violet/magenta iridescence (consistency, not forced camera focus)
  - subtle clean-edged gold alien spots (day shimmer, night richer reflective,
    NOT glowing)
  - very faint iridescent subdermal vein-map at temples/neck (reflective not glowing)
  - optional rare subtle nictitating membrane blink

PROMPT GUARDRAILS (his list, use them):
  - no pin-up posing
  - no sexual framing / crotch emphasis / camel toe
  - documentary realism
  - no text, subtitles or logos
  - avoid eye-colour drift, glowing, anime
  - avoid exaggerated proportions

HOW THIS SITS WITH HER EARLIER ANCHOR:
  * EYES. Her 2026-08-08 anchor line reads "deep-purple and gold double-ringed
    fractal irises". This spec makes the BASE COLOUR explicit: HAZEL-GREEN, with the
    double ring and fractal pattern still present and the purple now described as a
    faint VIOLET/MAGENTA IRIDESCENCE rather than the dominant colour. That matches
    his 2026-08-07 native-resolution ruling (hazel/olive-gold centre, thick beaded
    violet-purple outer ring). Read the anchor's "deep-purple" as the ring, not the
    whole iris. NON-GLOWING remains absolute.
  * SPOTS. "Subtle, clean-edged, gold" and explicitly NOT glowing -- day shimmer,
    night richer and reflective. Consistent with the temples-AND-cheekbones ruling.
  * NEW, not previously recorded anywhere: the faint iridescent subdermal VEIN-MAP at
    temples and neck (reflective, not glowing), and the rare NICTITATING MEMBRANE
    blink. Both are optional/subtle, neither glows.
  * NEW: age 26 reading ~22; Afro-Latina; athletic curvy with NATURAL proportions;
    and the character note -- capable, unaware of her own sexiness, matter-of-fact
    military confidence with slight bravado.

NOTE ON REFERENCES: he is regenerating Bia on Higgsfield as of 2026-08-10, so the
staged local refs (bia_face.png = "Bia Face upclose.png", bia_body.png = "Bia full
front A.png") are the OLD generation. Replace them with his new frames once he has
them -- for Kontext the reference governs canon, not the prompt.
"""

REPO = pathlib.Path(__file__).resolve().parent.parent
MARKER = "*** BIA -- EXPANDED SPEC. BARRY, 2026-08-10"


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
