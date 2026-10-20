"""
Re-file the design skills so the right agents can actually reach them.

All seven were seeded to `private:Creative` -- Vivian only. Three of them are
not visual work at all, so nobody who needs them can see them:

  ux-copy            -> its own text says it complements Derek's copywriting
  research-synthesis -> mining reviews / support tickets: Derek + Amara
  user-research      -> talking to customers: Derek + Amara

Placement rules used:
  * ux-copy -> domain:marketing. Creative already holds the `marketing` grant
    (see agent_domains), so Vivian KEEPS it and Derek + Elliot gain it.
  * research-synthesis + user-research -> a bare shared category, because no
    single domain reaches both Derek (marketing) and Amara (business_ops).
    They stay `.md`, so the cost to everyone else is one index line.

The four genuinely-visual skills stay private:Creative and are pinned in
agents.py.

Dry run by default. Pass --apply to commit. Prints a restore hint either way.
"""
import os
import sqlite3
import sys

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "brain.db")

MOVES = {
    "ux-copy.md": "domain:marketing",
    "research-synthesis.md": "knowledge:customer_research",
    "user-research.md": "knowledge:customer_research",
}
STAYS = ["design-critique.md", "accessibility-review.md", "design-system.md", "design-handoff.md"]


def main():
    apply = "--apply" in sys.argv
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    print("BEFORE")
    for name in list(MOVES) + STAYS:
        for r in conn.execute(
            "SELECT id, category, source_name FROM facts WHERE status='active' AND source_name=?",
            (name,),
        ):
            print(f"  id={r['id']:<5} {r['source_name']:<26} {r['category']}")

    print("\nPLANNED MOVES")
    for name, new_cat in MOVES.items():
        row = conn.execute(
            "SELECT id, category FROM facts WHERE status='active' AND source_name=?", (name,)
        ).fetchone()
        if not row:
            print(f"  {name}: NOT FOUND -- skipped")
            continue
        if row["category"] == new_cat:
            print(f"  {name}: already {new_cat} -- no change")
            continue
        print(f"  {name}: {row['category']}  ->  {new_cat}   (restore: UPDATE facts SET "
              f"category='{row['category']}' WHERE id={row['id']};)")
        if apply:
            conn.execute("UPDATE facts SET category=? WHERE id=?", (new_cat, row["id"]))

    if apply:
        conn.commit()
        print("\nAPPLIED. Facts are read fresh per call -- no restart needed for this part.")
        print("\nAFTER")
        for name in list(MOVES) + STAYS:
            for r in conn.execute(
                "SELECT id, category, source_name FROM facts WHERE status='active' AND source_name=?",
                (name,),
            ):
                print(f"  id={r['id']:<5} {r['source_name']:<26} {r['category']}")
    else:
        print("\nDRY RUN -- nothing changed. Re-run with --apply to commit.")
    conn.close()


if __name__ == "__main__":
    main()
