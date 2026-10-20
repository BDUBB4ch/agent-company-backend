"""Replace Elliot's director skill with Barry's own persona (2026-08-20).

Barry pasted a full "Director Agent System Prompt / Persona" and said: "Make this his
new skill. get rid of the old director skill."

OUT: fact 638 `scifi-action-drama-directing.md` -- 10,852 chars, CLAUDE-WRITTEN on
     2026-08-13. Set status='superseded', NOT deleted. Precedent: Claude's own
     wordings have no standing once Barry's exist, but rows are never hard-deleted.
IN:  knowledge/director-persona.md -- his text verbatim, ASCII punctuation only.

Also swaps the pin in agents.py so Elliot loads the new one. PIN CHANGES NEED A
BACKEND RESTART (unlike brain edits, which are live).

Re-runnable. Written as a script file, never through bash -c.
"""
import pathlib
import sqlite3
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import memory

DB = REPO / "data" / "brain.db"
NEW_DOC = REPO / "knowledge" / "director-persona.md"
OLD_FACT_ID = 638
OLD_SOURCE = "scifi-action-drama-directing.md"
NEW_SOURCE = "director-persona.md"


def main() -> None:
    content = NEW_DOC.read_text(encoding="utf-8")
    conn = sqlite3.connect(DB)

    # --- back up the outgoing skill before touching anything ---------------
    row = conn.execute(
        "SELECT source_name, status, content FROM facts WHERE id = ?", (OLD_FACT_ID,)
    ).fetchone()
    if row is None:
        raise SystemExit(f"fact {OLD_FACT_ID} not found -- nothing written.")
    src, status, old_content = row
    if OLD_SOURCE not in src:
        raise SystemExit(f"fact {OLD_FACT_ID} is '{src}', not the director skill. Aborting.")

    bak = REPO / "data" / f"backup_fact{OLD_FACT_ID}_{OLD_SOURCE}_before_replace_2026-08-20.md"
    if not bak.exists():
        bak.write_text(old_content, encoding="utf-8")
        print(f"backup: {bak.name} ({len(old_content):,} chars, was status={status})")

    # --- add the new skill (idempotent) ------------------------------------
    existing = conn.execute(
        "SELECT id FROM facts WHERE source_name = ? AND status = 'active'", (NEW_SOURCE,)
    ).fetchone()
    if existing:
        conn.execute("UPDATE facts SET content = ? WHERE id = ?", (content, existing[0]))
        conn.commit()
        print(f"fact {existing[0]} ({NEW_SOURCE}) updated -> {len(content):,} chars")
    else:
        new_id = memory.add_fact(
            category="private:MovieDirector",
            content=content,
            source_name=NEW_SOURCE,
            title="DIRECTOR AGENT -- SYSTEM PROMPT / PERSONA (Barry's words, 2026-08-20)",
        )
        print(f"fact {new_id} ({NEW_SOURCE}) created -> {len(content):,} chars")

    # --- retire the old one -------------------------------------------------
    conn.execute("UPDATE facts SET status = 'superseded' WHERE id = ?", (OLD_FACT_ID,))
    conn.commit()
    print(f"fact {OLD_FACT_ID} ({OLD_SOURCE}) -> status='superseded' (reversible)")

    # --- verify -------------------------------------------------------------
    still_active = conn.execute(
        "SELECT id FROM facts WHERE source_name = ? AND status = 'active'", (OLD_SOURCE,)
    ).fetchall()
    assert not still_active, f"old skill still active: {still_active}"
    live = conn.execute(
        "SELECT id, length(content) FROM facts WHERE source_name = ? AND status = 'active'",
        (NEW_SOURCE,),
    ).fetchone()
    assert live, "new skill is not active"
    print(f"verified: {NEW_SOURCE} active (fact {live[0]}, {live[1]:,} chars), "
          f"{OLD_SOURCE} retired")
    print("\nNEXT: pin swap in agents.py + backend restart (pins are not live-reloaded).")


if __name__ == "__main__":
    main()
