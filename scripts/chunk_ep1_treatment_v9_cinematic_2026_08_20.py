"""Install Barry's V9 CINEMATIC REWRITE (pasted 2026-08-20, his words: "I like
this version better") as the V9 of record: updates fact 691 (full treatment)
and the six ep1-v9-* act chunks from data/ep1_treatment_v9_verbatim.md.

Text is stored VERBATIM -- this script adds headers/routing lines only, changes
no words. The prior V9 is backed up at
data/backup_ep1_v9_before_cinematic_rewrite_2026-08-20.md (disk) and
data/backup_fact691_v9_before_cinematic_rewrite_2026-08-20.md (fact 691).

Section markers changed from the old V9 ("### ACT ONE ..." / "**SCENE A ...**")
to markdown H2 ("## ACT ONE ..." / "## SCENE A ...") -- this script and the
matching main.py anchor-extraction fix both handle the new format.
Re-runnable: upserts by source_name.
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
* THE WHOLE SCRIPT is rewritten in the format of Barry's exemplar
  (ep1-v9-format-exemplar -- match it field for field): block header
  "SHOT NN -- NAME | duration | MUSIC: ..." then "GENRE: ... | SPEED RAMP: ...",
  the slug, rich action prose, then CAMERA:, ENVIRONMENT & LIGHTING: (materials,
  light sources, texture -- a designed place, not a backdrop), EXPRESSION: (per
  character in frame), NEG:. INTERNAL MONOLOGUE labelled inline where the
  treatment has it. B-ROLL blocks are legitimate for establishing beats.
  Dialogue from this treatment VERBATIM. When Barry asks for a shot's PROMPT,
  it comes back as a Seedance 2.5 ```image``` fence, grounded in this text.
* @ HANDLES: first mention of a character in EVERY block is their @handle
  (@B-DUBB-new, @Tazz...), and every prompt carries it -- pronouns after that
  are fine (Barry, 2026-08-21: "as long as he uses the @ it should work").
  The production script's CHARACTER ANCHORS block (pass 1) is written from
  CURRENT canon in barry-character-canon, never from the treatment's anchor
  text alone. If the treatment and the canon disagree, the canon wins.
* ONE BEAT PER BLOCK, NO SPILL. Each SHOT covers ONLY its own moment -- never
  repeat or preview another block's prose. If a beat is already written in a
  previous block, it is DONE -- move forward.
* WHAT "REWRITE" MEANS IN THIS SEAT -- Barry, 2026-08-21, his words: "hes only
  supposed to rewrite my scripts, but with his skills. not reword my shit just
  add depth and lighting and camera angles and shit. make the scenes more
  lively. not a total rewrite."
  HIS SENTENCES ARE THE SPINE. Keep his prose and every line of his dialogue
  AS HE WROTE IT -- never paraphrase it, never "improve" his wording, never
  reorder his events. YOUR JOB IS THE CRAFT LAYER AROUND HIS WORDS. New
  EVENTS never happen unless Barry asks for your ideas -- and then they are
  offered clearly as yours, for him to keep or cut.
* INTRICATE ENVIRONMENTS (Barry, 2026-08-21: "I like intricate environment
  designs and details"). Every block's environment is a designed place, not a
  backdrop; foreground, midground, background all doing work.
* KNOWN CANON CONFLICTS IN THIS TREATMENT, flagged not fixed -- when writing
  these blocks, substitute per the standing rulings unless Barry says keep:
  (1) Yannah's "forearm controller" (lab door + Scene G) -- she has NO forearm
  unit in EP1 (that beat comes later, Keth helps her with it); use her
  handheld scanner / comms unit, as this same treatment does elsewhere.
  (2) The lab-scene Keth line "no iris, no white, just all-dark pools" -- the
  superseded eye wording; canon is dark green iris + dark pupil, no whites
  (this treatment's own anchor has it right).
* Work in passes: 3-5 blocks per reply, checkpoint, wait for Barry's go.
"""

FULL_HEADER = (
    "EP1 WRONG BOX -- V9 TREATMENT, CINEMATIC REWRITE (BARRY, 2026-08-20)\n"
    'EP1 "WRONG BOX" -- V9 DIRECTOR\'S TREATMENT -- FULL CINEMATIC REWRITE '
    "(Barry pasted and blessed this version 2026-08-20: \"I like this version "
    "better.\" It supersedes the earlier V9 text.)\n"
    "USE WHEN: any ask about the V9 treatment as a whole; the act/scene chunks "
    "(ep1-v9-*) carry the working text for conversion passes.\n\n"
    "THIS IS THE EPISODE'S SOURCE DOCUMENT. Dialogue and events are locked; "
    "production passes add the craft layer, never reword Barry's lines.\n\n"
    "--- TREATMENT TEXT, VERBATIM ---\n\n"
)

# (source_name, USE WHEN line, start marker, end marker or None=EOF)
CHUNKS = [
    ("ep1-v9-act1-colorado.md",
     "USE WHEN: writing V9 Act One (Colorado -- the run, climb, fence, corridor) as production script shots.",
     "## ACT ONE — COLORADO", "## ACT TWO"),
    ("ep1-v9-act2-intercut.md",
     "USE WHEN: writing V9 Act Two (the intercut -- Tazz's brawl, the overwhelm, B Dubb listening, the non-lethal missile volley, Bia/Yannah corridor fight, Keth rescue, the crate) as production script shots.",
     "## ACT TWO — THE INTERCUT", "## ACT THREE"),
    ("ep1-v9-act3-standoff.md",
     "USE WHEN: writing V9 Act Three (cargo hold, the eruption, the standoff, bargain-or-bleed) as production script shots.",
     "## ACT THREE — THE TALIA", "## SCENE A — THE DEBRIEF"),
    ("ep1-v9-scenes-abc.md",
     "USE WHEN: writing V9 Scenes A-C (the debrief, the tour, the bridge and daughter beat, his quarters) as production script shots.",
     "## SCENE A — THE DEBRIEF", "## SCENE D — THE NEXT DAY"),
    ("ep1-v9-scene-d-roach-fight.md",
     "USE WHEN: writing V9 Scene D -- the Keth and B Dubb fight, the roach insult and the chase -- as production script shots. Barry ruled this fight IS in, at Scene D.",
     "## SCENE D — THE NEXT DAY", "## SCENE E — TAZZ'S WOUNDS"),
    ("ep1-v9-scenes-e-h-end.md",
     "USE WHEN: writing V9 Scenes E-H (Tazz's wounds, the viewport conversation, FTL drop, the Araxys arrival, end card) as production script shots.",
     "## SCENE E — TAZZ'S WOUNDS", None),
]


def upsert(conn, source_name, content, title):
    existing = conn.execute(
        "SELECT id FROM facts WHERE source_name=? AND status='active'",
        (source_name,)).fetchone()
    if existing:
        conn.execute("UPDATE facts SET content=? WHERE id=?", (content, existing[0]))
        conn.commit()
        print(f"updated  {source_name:36} {len(content):>6,} chars")
    else:
        memory.add_fact(category="private:MovieDirector", content=content,
                        source_name=source_name, title=title)
        print(f"created  {source_name:36} {len(content):>6,} chars")


def main() -> None:
    text = SRC.read_text(encoding="utf-8")
    conn = sqlite3.connect(REPO / "data" / "brain.db")

    # Full treatment fact (691) -- the document of record.
    upsert(conn, "ep1-treatment-v9.md", FULL_HEADER + text,
           "EP1 V9 treatment -- cinematic rewrite, full text")

    for source_name, use_when, start, end in CHUNKS:
        i = text.find(start)
        assert i >= 0, f"start marker not found: {start}"
        j = text.find(end) if end else len(text)
        assert j > i, f"end marker not found: {end}"
        body = text[i:j].rstrip()
        content = (
            f"EP1 V9 TREATMENT (Barry, 2026-08-20 -- cinematic rewrite, blessed) -- {source_name.replace('.md','')}\n"
            f"{use_when}\n\n{RULES}\n"
            f"--- TREATMENT TEXT, VERBATIM ---\n\n{body}\n"
        )
        upsert(conn, source_name, content,
               f"EP1 V9 treatment -- {source_name.replace('.md','')}")

    block = memory.brain_context_block("MovieDirector")
    for source_name, *_ in CHUNKS:
        slug = source_name.replace(".md", "")
        assert slug in block, f"{slug} missing from index"
    print("verified: all six chunks in Elliot's index with routing lines")

    # Sanity: the anchors block main.py extracts must exist in the new fact.
    full = conn.execute(
        "SELECT content FROM facts WHERE source_name='ep1-treatment-v9.md' AND status='active'"
    ).fetchone()[0]
    a0 = full.find("## CHARACTER ANCHORS")
    a1 = full.find("## MUSIC ARCHITECTURE")
    assert 0 <= a0 < a1, "anchor markers not found in stored fact"
    print(f"verified: anchors block extractable ({a1 - a0:,} chars)")


if __name__ == "__main__":
    main()
