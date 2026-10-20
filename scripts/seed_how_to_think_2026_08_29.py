"""Seed knowledge/how-to-think.md to ALL NINE agents (category knowledge:thinking,
bare shared category = everyone, deliberately including Taliyah and Elliot --
reasoning discipline is not commercial content, and Elliot's confess-without-
fixing habit is a prime target).

Barry, 2026-08-29: "Can you create a skill that gives them as much of the
reasoning ability or the way you reason and think?" On-demand (.md) with a
USE WHEN routing line; the always-on half of this lives in agents.py's
_CONFIRMS_UNDERSTANDING mistake-protocol extension (same session).
Re-runnable: upserts by (source_name, category).
"""
import sys, os, sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import memory  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
FNAME = "how-to-think.md"
SRC = os.path.join(ROOT, "knowledge", FNAME)
CATEGORY = "knowledge:thinking"
TITLE = "How to think -- verify before claiming, break your own work, one-line post-mortems, root cause over symptom"

content = open(SRC, encoding="utf-8").read()

db = sqlite3.connect(memory.DB_PATH)
row = db.execute(
    "SELECT id, length(content) FROM facts WHERE source_name=? AND category=? AND status='active'",
    (FNAME, CATEGORY),
).fetchone()
if row:
    db.execute("UPDATE facts SET content=? WHERE id=?", (content, row[0]))
    db.commit()
    print(f"updated id={row[0]} {FNAME}: {row[1]} -> {len(content)} chars")
else:
    memory.add_fact(category=CATEGORY, content=content, source_name=FNAME, title=TITLE)
    nid = db.execute(
        "SELECT id FROM facts WHERE source_name=? AND category=? AND status='active'",
        (FNAME, CATEGORY),
    ).fetchone()
    print(f"CREATED id={nid[0] if nid else '?'} {FNAME}: {len(content)} chars")

print()
for office in ["CIO", "BusinessOps", "Engineer", "Taliyah", "MovieDirector"]:
    brain = memory.brain_context_block(office)
    hits = [l.strip()[:110] for l in brain.splitlines()
            if "how-to-think" in l and l.strip().startswith("- ")]
    print(f"{office:<14} sees {len(hits)}" + (f"  {hits[0]}" if hits else ""))
