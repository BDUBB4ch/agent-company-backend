"""Teach every agent the routing contract -- how their own filing makes recall fast.

2026-08-16, Barry: "instruct them to organize their own files so they know
where to look, and read it fast."

The filing-rules fact (id 608, shared, always-on) already explains the two
speeds and the categories. It never explained the ROUTING LINE -- which is
now the thing that decides whether a document reaches them automatically.
Appends that section rather than rewriting the fact.

Re-runnable: skips if already applied.
"""

import os
import sqlite3

MARKER = "ROUTING -- HOW A DOCUMENT FINDS YOU"

SECTION = """

ROUTING -- HOW A DOCUMENT FINDS YOU (this is what makes recall fast)
You do not dig through your shelf. Before every message, your own documents are
scored against what Barry just said, and the best matches are loaded for you
automatically -- you will see them under RECALLED FROM YOUR OWN MEMORY. That
matching runs on two fields only: the document's TITLE and its USE WHEN line.

So a document without a USE WHEN line is nearly invisible: it can only be found
by loose word matching against its whole body, which is both unreliable and
slow -- a wrongly loaded 50K document is context Barry waits for.

WHAT THIS MEANS WHEN YOU SAVE SOMETHING:
- ALWAYS give a note a when_useful (save_note's third argument). It becomes the
  note's USE WHEN line, and it is the only reason your future self will ever
  find it again.
- Write the USE WHEN in BARRY'S words -- the words he would actually type when
  he needs it, not a tidy label. "quarterly taxes, what to set aside, deductions"
  routes; "fiscal obligation guidance" never fires.
- Name the JOB, not the topic: "when writing a hook or caption for social" beats
  "about marketing".
- Give a specific title. "note-supplier-vetting-checklist" is findable;
  "note-thoughts" is not.
- One subject per note. A note covering four unrelated things routes badly on
  all four, and loads three irrelevant sections every time it fires.
- If you notice one of your own notes is stale or wrong, say so -- an old note
  that still routes is worse than no note.
"""


def main():
    db = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "brain.db")
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT id, content FROM facts WHERE status='active' "
        "AND content LIKE '%HOW YOUR BRAIN IS FILED%' LIMIT 1").fetchone()
    if not row:
        print("Filing-rules fact not found -- nothing changed.")
        return
    fid, content = row
    if MARKER in content:
        print(f"Fact {fid} already carries the routing section.")
        return
    conn.execute("UPDATE facts SET content=? WHERE id=?", (content.rstrip() + SECTION, fid))
    conn.commit()
    new_len = conn.execute("SELECT length(content) FROM facts WHERE id=?", (fid,)).fetchone()[0]
    conn.close()
    print(f"Fact {fid} updated: {len(content):,} -> {new_len:,} chars (all 9 agents, always-on).")


if __name__ == "__main__":
    main()
