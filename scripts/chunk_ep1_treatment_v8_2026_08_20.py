"""Chunk the V8 treatment into act-sized facts so auto-recall can actually serve it.

MEASURED FAILURE (2026-08-20, same session it was seeded): asked for Act One as
production blocks, Elliot INVENTED a fence-crash that exists in neither V7 nor V8.
Why: the single ep1-treatment-v8.md fact is 31,882 chars against RECALL_BUDGET
20,000 -- recall NAMES an over-budget doc but never injects it, and read_skill
fires ~1% of the time. He was told the doc existed and wrote from imagination.

Fix: split into six chunks, each well under budget, each with a USE WHEN line
naming its act/scenes, so the relevant piece rides into his context WHOLE on the
message that needs it. The un-chunked original is superseded (kept, never deleted).
Body text remains VERBATIM -- splitting adds headers, changes no words.
"""
import pathlib
import sqlite3
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import memory

SRC = REPO / "data" / "ep1_treatment_v9_verbatim.md"

RULES = """RULES FOR WRITING THIS AS A PRODUCTION SCRIPT (Barry, 2026-08-20):
* Target format is the V7 block, EVERY field: "SHOT N -- NAME | duration | MUSIC:"
  then GENRE + SPEED RAMP, scene slug, action prose, CAMERA: line, EXPRESSION:
  per character in frame, NEG: line. Dialogue from this treatment VERBATIM.
* @ HANDLES: first mention of a character in EVERY block is their @handle
  (@B-DUBB-new, @Tazz...), and every prompt carries it -- pronouns after that
  are fine (Barry, 2026-08-21: "as long as he uses the @ it should work").
  The production script's CHARACTER ANCHORS block (pass 1) is written from
  CURRENT canon (the treatment's own anchors match it as of 2026-08-21).
* ONE BEAT PER BLOCK, NO SPILL. Each SHOT covers ONLY its own moment -- never
  repeat or preview another block's prose (measured: Shot 02 swallowed the
  whole climb and Shot 03 then repeated it nearly verbatim). If a beat is
  already written in a previous block, it is DONE -- move forward.
* THE TREATMENT'S CHARACTER ANCHORS WERE UPDATED TO CURRENT CANON 2026-08-21 --
  they are live now, not stale. If they and barry-character-canon ever
  disagree, the canon wins.
* WHAT "REWRITE" MEANS IN THIS SEAT -- Barry, 2026-08-21, his words: "hes only
  supposed to rewrite my scripts, but with his skills. not reword my shit just
  add depth and lighting and camera angles and shit. make the scenes more
  lively. not a total rewrite."
  HIS SENTENCES ARE THE SPINE. Keep his prose and every line of his dialogue
  AS HE WROTE IT -- never paraphrase it, never "improve" his wording, never
  reorder his events. YOUR JOB IS THE CRAFT LAYER AROUND HIS WORDS: the
  camera and lens on every beat, the lighting and where it comes from, sound
  design, each character's expression and body language, atmosphere and depth
  of frame -- the production fields and the connective tissue that make his
  scene breathe on screen. His text + your eye = the block. A fake
  fence-crash got invented into Act One once; new EVENTS never happen unless
  Barry asks for your ideas ("what do you think", "add something", "pitch
  me") -- and then they are offered clearly as yours, for him to keep or cut.
* INTRICATE ENVIRONMENTS (Barry, 2026-08-21: "I like intricate environment
  designs and details"). Every block's environment is a designed place, not a
  backdrop: what the surfaces are made of, what the light touches, what is
  worn, stacked, leaking, humming, labelled or deliberately unlabelled -- the
  three or four specific details that make the room feel engineered and lived
  in. Depth of frame: foreground, midground, background all doing work.
* Work in passes: 3-5 blocks per reply, checkpoint, wait for Barry's go.
"""

# (source_name, USE WHEN line, start marker, end marker or None=EOF)
CHUNKS = [
    ("ep1-v9-act1-colorado.md",
     "USE WHEN: writing V9 Act One (Colorado -- the run, climb, fence, corridor) as production script shots.",
     "### ACT ONE — COLORADO", "### ACT TWO"),
    ("ep1-v9-act2-intercut.md",
     "USE WHEN: writing V9 Act Two (the intercut -- Tazz's brawl, the overwhelm, B Dubb listening, the non-lethal missile volley, Bia/Yannah corridor fight, Keth rescue, the crate) as production script shots.",
     "### ACT TWO — THE INTERCUT", "### ACT THREE"),
    ("ep1-v9-act3-standoff.md",
     "USE WHEN: writing V9 Act Three (cargo hold, the eruption, the standoff, bargain-or-bleed) as production script shots.",
     "### ACT THREE — THE TALIA", "**SCENE A — THE DEBRIEF**"),
    ("ep1-v9-scenes-abc.md",
     "USE WHEN: writing V9 Scenes A-C (the debrief, the tour, the bridge and daughter beat, his quarters) as production script shots.",
     "**SCENE A — THE DEBRIEF**", "**SCENE D — THE NEXT DAY"),
    ("ep1-v9-scene-d-roach-fight.md",
     "USE WHEN: writing V9 Scene D -- the Keth and B Dubb fight, the roach insult and the chase -- as production script shots. Barry ruled this fight IS in, at Scene D.",
     "**SCENE D — THE NEXT DAY", "**SCENE E — TAZZ'S WOUNDS**"),
    ("ep1-v9-scenes-e-h-end.md",
     "USE WHEN: writing V9 Scenes E-H (Tazz's wounds, the viewport conversation, FTL drop, the Araxys arrival, end card) as production script shots.",
     "**SCENE E — TAZZ'S WOUNDS**", None),
]


def main() -> None:
    text = SRC.read_text(encoding="utf-8")
    conn = sqlite3.connect(REPO / "data" / "brain.db")

    # The full-treatment fact STAYS ACTIVE since 2026-08-21 -- Barry retired
    # V7 and every older version, so ep1-treatment-v8.md is the episode's
    # document of record (with current anchors). The chunks exist purely so
    # recall can serve act-sized pieces; both live side by side.

    for source_name, use_when, start, end in CHUNKS:
        i = text.find(start)
        assert i >= 0, f"start marker not found: {start}"
        j = text.find(end) if end else len(text)
        assert j > i, f"end marker not found: {end}"
        body = text[i:j].rstrip()
        content = (
            f"EP1 V9 TREATMENT (Barry, 2026-08-21 -- V7+V8 combined, current canon) -- {source_name.replace('.md','')}\n"
            f"{use_when}\n\n{RULES}\n"
            f"--- TREATMENT TEXT, VERBATIM ---\n\n{body}\n"
        )
        existing = conn.execute(
            "SELECT id FROM facts WHERE source_name=? AND status='active'",
            (source_name,)).fetchone()
        if existing:
            conn.execute("UPDATE facts SET content=? WHERE id=?", (content, existing[0]))
            conn.commit()
            print(f"updated  {source_name:36} {len(content):>6,} chars")
        else:
            memory.add_fact(category="private:MovieDirector", content=content,
                            source_name=source_name,
                            title=f"EP1 V9 treatment -- {source_name.replace('.md','')}")
            print(f"created  {source_name:36} {len(content):>6,} chars")

    block = memory.brain_context_block("MovieDirector")
    for source_name, *_ in CHUNKS:
        slug = source_name.replace(".md", "")
        assert slug in block, f"{slug} missing from index"
    print("verified: all six chunks in Elliot's index with routing lines")


if __name__ == "__main__":
    main()
