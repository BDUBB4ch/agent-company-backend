"""Bia's figure -- Barry, 2026-08-10, immediately after the expanded spec.
His words, appended to BOTH canon copies (disk + facts.id=592).
"""
import pathlib
import sqlite3

SPEC = """

*** BIA -- FIGURE. BARRY, 2026-08-10. HIS WORDS: "make sure she has nice butt and breast" ***

Bia is CURVY where it counts: a full, shapely bust and full, shapely glutes, carried on the
athletic build already in her spec. This is part of her canon silhouette, not an optional
render accident -- if a render flattens her out, the render is wrong.

HOW THIS SITS WITH HIS OWN GUARDRAILS FROM THE SAME DAY -- both apply, they are not in
conflict:
  - "athletic curvy with NATURAL proportions" and "avoid exaggerated proportions" still
    stand. Full and shapely, NOT inflated, NOT cartoon, NOT balloon-like.
  - "no pin-up posing", "no sexual framing / crotch emphasis / camel toe" and "documentary
    realism" still stand. Her figure reads through BUILD and WARDROBE FIT, never through
    the camera leering -- no low angles up at her, no crotch or rear framing as the subject
    of the shot, no arched-back posing.
  - This matches the character note he already gave: "capable and unaware of her sexiness".
    She is attractive the way a real athletic woman is attractive, incidentally, while doing
    her job. The camera does not point it out.

PRACTICAL EFFECT ON REFERENCES: the strongest lever is the BODY reference, not the prompt --
for Kontext the reference governs the silhouette. Choose a full-body frame that shows the
figure he wants, and the render inherits it.
"""

REPO = pathlib.Path(__file__).resolve().parent.parent
MARKER = "*** BIA -- FIGURE. BARRY, 2026-08-10"


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
