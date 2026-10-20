"""ELLIOT CLEANUP -- Barry, 2026-08-15: "clean up what he has, he has old or
duplicates, probably."

Two SAFE changes only. Nothing Barry authored is edited or deleted; no fact is
removed; every change is one SQL line to undo, printed below.

1. REVOKE the marketing + engineering domain grants from MovieDirector.
   They put 24 skills / 106,049 chars of SEO audits, email sequences, code
   review, deploy checklists and tech debt into the movie director's skill
   index. None of them is pinned; none is his job. The facts stay exactly where
   they are and every other agent keeps them -- this only stops routing them to
   him. His index is how read_skill finds anything, and 24 wrong titles in it is
   the thing that makes the right one hard to find.
   Deliberately NOT touched: prompt-engineering also disappears with the
   engineering grant, which is correct -- CLAUDE.md already calls it "Sophie's
   reference for TEXT prompting, 10.8K chars of active misdirection in this seat".

2. MOVE five stale auto-summaries + one approved-idea note + one empty fact OFF
   the always-on shelf, by giving them a .md source_name (memory._is_skill_fact
   keys on that). Nothing is deleted -- the text stays readable via read_skill.
   Keeps the newest summary always-on for continuity, which is the documented
   pattern from the 2026-08-03 cleanup.
   Fact 653 (28 chars, "Auto-summarized conversation") is content-free and is
   the one exception: superseded, not renamed.
"""
import sqlite3
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
KEEP_ALWAYS_ON = 654  # newest real summary, kept for conversational continuity


def main() -> None:
    conn = sqlite3.connect(REPO / "data" / "brain.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    grants = [r["domain"] for r in cur.execute(
        "SELECT domain FROM agent_domains WHERE office_name='MovieDirector'")]
    for d in ("marketing", "engineering"):
        if d in grants:
            cur.execute("DELETE FROM agent_domains WHERE office_name='MovieDirector' AND domain=?", (d,))
            print(f"revoked domain grant: {d}")
            print(f"  UNDO: INSERT INTO agent_domains (office_name, domain) VALUES ('MovieDirector','{d}');")
        else:
            print(f"domain grant {d}: already absent")

    rows = cur.execute(
        "SELECT id, source_name, length(content) n FROM facts "
        "WHERE status='active' AND category='private:MovieDirector' "
        "AND (source_name IS NULL OR source_name NOT LIKE '%.md')").fetchall()
    for r in rows:
        if r["id"] == KEEP_ALWAYS_ON:
            print(f"fact {r['id']}: kept always-on (newest summary, continuity)")
            continue
        if r["id"] == 653 and r["n"] < 60:
            cur.execute("UPDATE facts SET status='superseded' WHERE id=?", (r["id"],))
            print(f"fact {r['id']}: superseded ({r['n']} chars, content-free)")
            print(f"  UNDO: UPDATE facts SET status='active' WHERE id={r['id']};")
            continue
        old = r["source_name"]
        new = f"conversation-history-{r['id']}.md" if not old else f"{old.rstrip('.')}.md"
        cur.execute("UPDATE facts SET source_name=? WHERE id=?", (new, r["id"]))
        print(f"fact {r['id']}: always-on -> on-demand as {new} ({r['n']:,} chars, kept)")
        print(f"  UNDO: UPDATE facts SET source_name={'NULL' if old is None else repr(old)} WHERE id={r['id']};")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
