"""Install the full Seedance 2.5 skill set for Elliot -- Barry, 2026-08-15:
"just give elliot the skills and let him decide how to use it all. All Of It"

Seeds seedance-production-tasks (new) and re-syncs seedance-prompting (expanded
with the official camera + performance material and the directing blend).

PINNED, not on-demand, deliberately: read_skill fires in ~1% of calls, so
on-demand is gatekeeping with extra steps. Barry's instruction is that Elliot
holds all of it and decides himself.

Re-runnable: upserts by source_name.
"""
import pathlib
import sqlite3

REPO = pathlib.Path(__file__).resolve().parent.parent
FILES = {
    "seedance-prompting.md": "private:MovieDirector",
    "seedance-production-tasks.md": "private:MovieDirector",
    "seedream-image-generation.md": "private:MovieDirector",
}


def main() -> None:
    conn = sqlite3.connect(REPO / "data" / "brain.db")
    cur = conn.cursor()
    for name, category in FILES.items():
        body = (REPO / "knowledge" / name).read_text(encoding="utf-8")
        row = cur.execute(
            "SELECT id, length(content) FROM facts WHERE source_name=? AND status='active'",
            (name,)).fetchone()
        if row:
            cur.execute("UPDATE facts SET content=? WHERE id=?", (body, row[0]))
            print(f"  updated  id={row[0]:<5} {name:<34} {row[1]:>6,} -> {len(body):,} chars")
        else:
            cur.execute(
                "INSERT INTO facts (category, content, source_name, status, created_at) "
                "VALUES (?,?,?, 'active', datetime('now'))", (category, body, name))
            print(f"  created  id={cur.lastrowid:<5} {name:<34} {len(body):>6,} chars  [{category}]")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
