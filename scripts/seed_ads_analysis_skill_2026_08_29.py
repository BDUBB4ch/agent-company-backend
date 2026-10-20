"""Seed knowledge/commerce/ads-performance-analysis.md into the brain.

Barry, 2026-08-29: agents must ANALYZE ad numbers before reporting them --
"i want them to understand what it means... corporate level shit."

Category knowledge:commerce (business seats see it; Taliyah + MovieDirector
excluded via _SHARED_CATEGORY_EXCLUSIONS). .md = on-demand, USE WHEN routed.
Re-runnable: upserts by (source_name, category), same pattern as
seed_commerce_skills_2026_08_13.py.
"""
import sys, os, sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import memory  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
FNAME = "ads-performance-analysis.md"
SRC = os.path.join(ROOT, "knowledge", "commerce", FNAME)
CATEGORY = "knowledge:commerce"
TITLE = "Ads performance analysis -- reading Microsoft Ads numbers like an operator, runway, breakeven ROAS by margin line"

content = open(SRC, encoding="utf-8").read()

db_path = memory.DB_PATH if hasattr(memory, "DB_PATH") else os.path.join(ROOT, "data", "brain.db")
db = sqlite3.connect(db_path)

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

# Verify: routed index line visible to business seats, absent for Taliyah/Elliot.
print()
for office in ["BusinessOps", "Marketing", "CIO", "Operations", "Taliyah", "MovieDirector"]:
    brain = memory.brain_context_block(office)
    hits = [l.strip()[:120] for l in brain.splitlines()
            if "ads-performance-analysis" in l and l.strip().startswith("- ")]
    print(f"{office:<14} sees {len(hits)}"
          + (f"  {hits[0]}" if hits else ""))
