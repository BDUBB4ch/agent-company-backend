"""Build Elliot's CHARACTER ANCHORS CARD -- the always-on core that replaces
the full 100K-char canon pin (Barry, 2026-08-21: "maybe we got them reading
shit too much... they should know their jobs" -> approved option 1).

EXTRACTION, NOT AUTHORSHIP: every body line is copied VERBATIM from
data/barry-character-canon.md (Barry's words). Zero paraphrase -- the same
sanctioned pattern as the mega-write anchors extraction. The FULL canon bible
(props A/B prompts, voice bible passes, history, superseded records) stays an
active on-demand skill reachable via recall/read_skill.

Card contents (verbatim slices, verified by marker assertions):
  1. The six character anchors  (@B DUBB ... @VORSHARA + its notes)
  2. THE NAMES ROSTER            (handles, locations, @TALIA ruling)
  3. WHO CARRIES WHAT            (weapon pairing map + the swap-as-you-write rule)

Re-runnable: upserts by source_name. Sync rule: if the canon changes, re-run
this script -- the card is DERIVED, never hand-edited.
"""
import pathlib
import sqlite3
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import memory

SRC = REPO / "data" / "barry-character-canon.md"
CARD_SOURCE = "character-anchors-card.md"

HEADER = (
    "CHARACTER ANCHORS CARD -- BARRY'S WORDS, VERBATIM (derived 2026-08-21)\n"
    "This card is your always-on core: the six character anchors, the names\n"
    "roster, and the weapon pairing map, copied VERBATIM from\n"
    "barry-character-canon. Copy anchors exactly -- never paraphrase, never\n"
    "'improve', never derive from a render; where a render disagrees, the\n"
    "RENDER is wrong. The FULL canon bible (weapon A/B prop prompts, the\n"
    "voice bible with Barry's directions, history and superseded records) is\n"
    "on-demand: read_skill barry-character-canon, or recall serves it.\n"
    "This card is regenerated from the canon by\n"
    "scripts/build_anchors_card_2026_08_21.py -- never hand-edit it.\n\n"
)


def main() -> None:
    text = SRC.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    def slice_between(start_marker: str, end_marker: str) -> str:
        i = text.find(start_marker)
        j = text.find(end_marker)
        assert i >= 0, f"start marker missing: {start_marker!r}"
        assert j > i, f"end marker missing/misordered: {end_marker!r}"
        return text[i:j].rstrip() + "\n"

    anchors = slice_between("@B DUBB: MEDIUM-BUILD, SLIGHTLY MUSCULAR",
                            "@BIA — Leader")
    roster = slice_between("THE NAMES ROSTER -- USE THESE NAMES",
                           "WHO CARRIES WHAT -- CHECK THIS BEFORE YOU WRITE A SHOT")
    # who-carries section: end at the line after the swap rule block.
    k = text.find("WHO CARRIES WHAT -- CHECK THIS BEFORE YOU WRITE A SHOT")
    assert k >= 0
    k_end = text.find("\n\n", text.find("SWAP AS YOU WRITE", k))
    assert k_end > k, "end of WHO CARRIES WHAT section not found"
    who = text[k:k_end].rstrip() + "\n"

    card = (
        HEADER
        + "=== THE SIX ANCHORS (verbatim) ===\n\n" + anchors
        + "\n=== " + roster
        + "\n=== " + who
    )
    # Sanity: the load-bearing strings must have survived extraction intact.
    for must in ("MEDIUM-BUILD", "@Bia-2", "@B-DUBB-new", "@Bia's-Pistol*",
                 "@Yannah's-Machine-Pistol", "@Tazz's-Weapon", "@TALIA",
                 "dark green", "four electric-blue eyes",
                 "revealing natural areola"):
        assert must in card, f"extraction lost required string: {must!r}"

    conn = sqlite3.connect(REPO / "data" / "brain.db")
    existing = conn.execute(
        "SELECT id FROM facts WHERE source_name=? AND status='active'",
        (CARD_SOURCE,)).fetchone()
    if existing:
        conn.execute("UPDATE facts SET content=? WHERE id=?", (card, existing[0]))
        conn.commit()
        print(f"updated  {CARD_SOURCE} {len(card):,} chars (id {existing[0]})")
    else:
        memory.add_fact(category="knowledge:talia_crew", content=card,
                        source_name=CARD_SOURCE,
                        title="Character anchors card -- Barry's words, always-on core")
        print(f"created  {CARD_SOURCE} {len(card):,} chars")


if __name__ == "__main__":
    main()
