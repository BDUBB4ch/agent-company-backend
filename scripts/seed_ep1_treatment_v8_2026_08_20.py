"""Seed the EP1 V8 director's treatment into Elliot's brain (2026-08-20).

Barry supplied the V8 treatment in chat and ruled: Elliot is to write V8 as a
PRODUCTION SCRIPT (the V7 shot-block format). This makes the treatment reachable --
until now it existed only in a Claude chat and Elliot had never seen it.

His rulings, baked into the header so Elliot cannot miss them:
  * The CHARACTER ANCHORS section in this treatment is OLD -- "ignor it here. the
    eyes and everything is the way we want it" -- current canon wins.
  * The Keth / B Dubb fight (the roach chase) goes in at Scene D.

Body is stored VERBATIM -- not one word of the treatment itself is changed.
On-demand (.md) with a USE WHEN routing line so recall serves it on V8 asks.
"""
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import memory

SOURCE_NAME = "ep1-treatment-v8.md"
DOC = REPO / "data" / "ep1_treatment_v8_verbatim.md"

HEADER = """EP1 "WRONG BOX" -- V8 DIRECTOR'S TREATMENT (supplied by Barry, 2026-08-20)
USE WHEN: writing V8 as a production script, converting the V8 treatment to shots, or any ask that mentions V8.

HOW TO USE THIS DOCUMENT -- BARRY'S RULINGS, 2026-08-20:
1. IGNORE THE "CHARACTER ANCHORS" SECTION BELOW ENTIRELY. It is old. His words:
   "character ancor is solid the way we changed it, so ignor it here. the eyes and
   everything is the way we want it." When writing the production script, the
   CHARACTER ANCHORS block comes from the CURRENT canon pinned in your context --
   medium-build B Dubb, Keth's dark green eyes, Yannah's new baseline (locs, gem
   stud, ear cuff, black suit, NO forearm controller), Tazz all-black sleeveless,
   the current weapon handles and voice locks.
2. THE KETH / B DUBB FIGHT (the roach chase in SCENE D below) IS IN. Place it at
   Scene D, where it sits in this treatment.
3. THE TARGET FORMAT IS THE V7 PRODUCTION SCRIPT TEMPLATE -- the shot-block shape
   you can read via read_scene/search_script: numbered SHOT / B-ROLL blocks, each
   with duration + MUSIC, GENRE, SPEED RAMP, scene slug, action prose, CAMERA:
   line, EXPRESSION: per character, and a NEG: line. Every shot gets the full
   block. Dialogue in this treatment is used VERBATIM.
4. WORK IN PASSES. A production script does not fit in one reply: convert 3-5
   shots per reply, checkpoint, continue when Barry says go -- the same pass
   discipline as long-form story writing.

--- THE V8 TREATMENT, VERBATIM, BEGINS BELOW ---

"""


def main() -> None:
    body = DOC.read_text(encoding="utf-8")
    assert "WRONG BOX" in body and "Roach" in body, "treatment body looks wrong"
    content = HEADER + body

    existing = [
        f for f in memory.get_active_facts_for_agent("MovieDirector")
        if f.get("source_name") == SOURCE_NAME
    ]
    if existing:
        import sqlite3
        conn = sqlite3.connect(REPO / "data" / "brain.db")
        conn.execute("UPDATE facts SET content = ? WHERE id = ?",
                     (content, existing[0]["id"]))
        conn.commit()
        print(f"updated fact {existing[0]['id']} ({SOURCE_NAME}) -> {len(content):,} chars")
    else:
        fid = memory.add_fact(
            category="private:MovieDirector",
            content=content,
            source_name=SOURCE_NAME,
            title="EP1 WRONG BOX -- V8 director's treatment (Barry, 2026-08-20)",
        )
        print(f"created fact {fid} ({SOURCE_NAME}) -> {len(content):,} chars")

    # verify it renders in his index with the routing line
    block = memory.brain_context_block("MovieDirector")
    assert "ep1-treatment-v8" in block, "not in Elliot's index"
    print("verified: in Elliot's skill index, on-demand, routed")


if __name__ == "__main__":
    main()
