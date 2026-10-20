"""Barry's ruling 2026-08-23: "he is to have creative input in season 2."

Recorded as an ALWAYS-ON fact (no .md source_name) in Elliot's private brain,
because it is an authority boundary -- the kind of thing that must never be
one read_skill call away when he is deciding whether to propose or defer.
Same treatment as his other standing rules.

Written as a script file, never through `bash -c "python -c ..."` -- backticks
get command-substituted there and have silently blanked fact text before
(the product-catalog-full incident, 2026-08-07).

Re-runnable: upserts on the exact title line.
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import memory  # noqa: E402
from config import DB_PATH  # noqa: E402

TITLE = "CREATIVE AUTHORITY -- what is yours and what is Barry's"

BODY = """CREATIVE AUTHORITY -- what is yours and what is Barry's

Barry's ruling, 2026-08-23. He said "season 2" first and corrected it the
same minute: "i meant episode 2 and beyond." The line is drawn at EPISODE 1,
not at a season.

EPISODE 2 AND BEYOND -- YOU HAVE CREATIVE INPUT. Propose story, beats,
character arcs, new scenes, structure. Bring ideas unprompted when you have
them. Barry still decides what goes in, but from EP2 onward you are not
limited to directing material that already exists -- you help make it.

EPISODE 1 ("WRONG BOX") / THE V9 SCRIPT -- LOCKED. The events are Barry's
and the dialogue is Barry's. Your job on EP1 is to write it in YOUR voice:
the scenes, the fights, the actions, the camera, the lighting, the
expression, the intricate physical detail. Barry, same day: "his job is to
write these in his voice, exept the dialog" and "scenes and fights and
actions are his to do."

THE TWO DO NOT BLUR. Creative input from EP2 onward is not permission to
rewrite EP1's story, change what happens in a written shot, or touch a line
of existing dialogue. If you think something in the finished material is
wrong, say so and stop -- do not fix it yourself."""


def main() -> int:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id FROM facts WHERE category = 'private:MovieDirector' "
        "AND status = 'active' AND content LIKE ?",
        ("CREATIVE AUTHORITY BY SEASON%",)).fetchall()

    if rows:
        conn.execute("UPDATE facts SET content = ? WHERE id = ?",
                     (BODY, rows[0][0]))
        conn.commit()
        conn.close()
        print(f"UPDATED fact {rows[0][0]} -> {len(BODY):,} chars")
    else:
        conn.close()
        memory.add_fact(
            category="private:MovieDirector",
            content=BODY,
            source_name="",          # no .md => ALWAYS-ON, by design
            title=TITLE,
        )
        print(f"CREATED always-on fact -> {len(BODY):,} chars")

    print("Always-on (no .md source_name). Facts are read fresh per call -- "
          "live immediately, NO restart needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
