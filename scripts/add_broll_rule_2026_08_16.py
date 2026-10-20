"""Store Barry's B-roll-vs-transition ruling in Elliot's brain, verbatim.

2026-08-16, said to Claude mid-session: the EP1 scripts' "B-ROLL" blocks
were his attempt at TRANSITION scenes, mislabelled. Elliot must know this
and be ready to rewrite them as transitions WHEN BARRY ASKS -- not before,
and rewrites go in Elliot's reply, never into the stored script (the
2026-08-14 substitute-never-edit ruling).

Written as a standing-rule fact (source_name 'standing-rule', always-on)
so it rides every message, same mechanism as chat-captured rules.
Re-runnable: skips if already stored.
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
import memory  # noqa: E402

BARRY_VERBATIM = (
    "the B roll scenes, I was trying to make transition scenes, not B roll. "
    "so make sure elliot knows he will have to rewrite that when i ask. "
    "he will have to do things like that for me a lot"
)

CONTENT = (
    "STANDING RULE from Barry (2026-08-16) about the B-ROLL blocks in his "
    "scripts -- follow this in every conversation:\n"
    f"\"{BARRY_VERBATIM}\"\n"
    "What this means in practice: the blocks labelled B-ROLL in the EP1 "
    "scripts are meant as TRANSITION scenes -- treat the label as his "
    "intent for a transition, and when he asks, rewrite them as proper "
    "transitions. Rewrites go in YOUR REPLY (use read_scene to fetch the "
    "block first, exactly as written) -- the stored script itself is never "
    "edited, per his substitute-never-edit ruling. Expect revision work "
    "like this often; it is a normal part of your job, not an exception."
)


def main():
    db = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "brain.db")
    conn = sqlite3.connect(db)
    exists = conn.execute(
        "SELECT id FROM facts WHERE source_name='standing-rule' AND status='active' "
        "AND category='private:MovieDirector' AND content LIKE '%B roll scenes%'"
    ).fetchone()
    conn.close()
    if exists:
        print(f"Already stored as fact {exists[0]} -- nothing to do.")
        return
    memory.add_fact(
        category="private:MovieDirector",
        content=CONTENT,
        source_name="standing-rule",
        title="STANDING RULE 2026-08-16 -- B-ROLL blocks are transitions",
    )
    print("Stored.")
    block = memory.brain_context_block("MovieDirector")
    print("rides always-on:", "B roll scenes" in block)


if __name__ == "__main__":
    main()
