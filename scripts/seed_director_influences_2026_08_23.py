"""Seed Barry's "Director Knowledge Injection Prompt" as Elliot's
`director-influences` skill (2026-08-23, Barry: "give him this too").

WHY IT EXISTS: measured the same day, the 27B genuinely KNOWS these six
references -- probed cold, it named John Wick's long uncut takes, Blade
Runner's rain-slicked neon, Shepard/N7, and correctly separated Jaa's
hand-to-hand from Woo's dual-wield gun-fu. So the names in his persona are
not dead tokens. What the persona never carried is WHAT BARRY WANTS FROM
each one -- the per-influence camera/tone/key-visual-rule breakdown. That is
this document, and it is his words.

Verbatim except: unicode punctuation normalised to ASCII (house practice),
and the operator-facing subtitle "(Paste this into your agent's system
instructions...)" dropped, since it addresses the human, not Elliot.

PLACEMENT, ruled by Barry in one line ("thats part of his persona"): the text
lives in agents.py's MOVIE_ID system_prompt, exactly like the director persona
he gave on 2026-08-20. This fact is the readable on-demand COPY of it and is
deliberately NOT pinned -- pinning would print the same ~5.9K chars twice on
every message. Identical reasoning to `director-persona`.

Re-runnable: upserts by source_name, so editing knowledge/director-influences.md
and re-running keeps disk and brain in sync (the two-copy drift that bit the
canon on 2026-08-08).
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import memory  # noqa: E402
from config import DB_PATH  # noqa: E402

SOURCE_NAME = "director-influences.md"
CATEGORY = "private:MovieDirector"
TITLE = "DIRECTOR KNOWLEDGE INJECTION -- the six influences and what each one demands"

DISK = os.path.join(os.path.dirname(__file__), "..",
                    "knowledge", "director-influences.md")


def main() -> int:
    with open(DISK, encoding="utf-8") as fh:
        body = fh.read().strip()

    non_ascii = sorted({c for c in body if ord(c) > 127})
    if non_ascii:
        print(f"REFUSING: non-ASCII characters present: {non_ascii}")
        return 1

    # memory.py has no update_fact -- in-place edits in this repo go through
    # a direct UPDATE (same as the canon fact 592 / seedance fact 593 scripts).
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id FROM facts WHERE source_name = ? AND status = 'active'",
        (SOURCE_NAME,)).fetchall()

    if rows:
        fact_id = rows[0][0]
        conn.execute("UPDATE facts SET content = ? WHERE id = ?",
                     (body, fact_id))
        conn.commit()
        conn.close()
        print(f"UPDATED fact {fact_id} ({SOURCE_NAME}) -> {len(body):,} chars")
        if len(rows) > 1:
            print(f"  WARNING: {len(rows)} active copies share this "
                  f"source_name -- ids {[r[0] for r in rows]}")
    else:
        conn.close()
        fact_id = memory.add_fact(
            category=CATEGORY,
            content=body,
            source_name=SOURCE_NAME,
            title=TITLE,
        )
        print(f"CREATED fact {fact_id} ({SOURCE_NAME}) -> {len(body):,} chars")

    print(f"\nCategory: {CATEGORY} (Elliot only -- Vivian does business "
          f"images, not the movie)")
    print("On-demand (.md) and deliberately NOT pinned: the live copy is in "
          "agents.py's MOVIE_ID persona. Restart the backend to load it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
