"""Seed the Innexo lab-results skill into the brain.

Category business:bdubbgrows -- shared with every business-facing seat, and
already excluded for Taliyah + MovieDirector via _SHARED_CATEGORY_EXCLUSIONS
(cannabis lab data is pure noise in those two contexts). On-demand (.md) with
a USE WHEN routing line. Re-runnable: upserts by (source_name, category).
"""
import sys, os, sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import memory  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
CATEGORY = "business:bdubbgrows"
FILES = [
    ("bionova-innexo-lab-results.md", "Bionova Innexo lab results -- the substantiation document"),
    ("bionova-coco-feeding-chart.md", "Bionova official coco feeding chart -- doses, EC, mixing order"),
    ("bionova-cost-basis.md", "Bionova cost basis -- real COGS for margin math (INTERNAL, never publish)"),
    ("bionova-wholesale-pricelist.md", "Bionova official wholesale list -- underpricing finding + Global Garden history (INTERNAL)"),
    ("bionova-suggested-retail-2025.md", "Barry own Oct-2025 US retail pricing plan + gap vs live store (INTERNAL)"),
    ("competitor-hydrobuilder.md", "Competitor Hydrobuilder.com -- pricing anchors, silica tier distinction, cost-per-feeding rule"),
    ("global-garden-wholesale-pricelist.md", "Global Garden full-catalog wholesale + SRP list (INTERNAL) -- non-Bionova COGS"),
]

db_path = memory.DB_PATH if hasattr(memory, "DB_PATH") else os.path.join(ROOT, "data", "brain.db")
db = sqlite3.connect(db_path)
for name, title in FILES:
    content = open(os.path.join(ROOT, "knowledge", "bdubb-products", name), encoding="utf-8").read()
    row = db.execute(
        "SELECT id, length(content) FROM facts WHERE source_name=? AND category=? AND status='active'",
        (name, CATEGORY),
    ).fetchone()
    if row:
        db.execute("UPDATE facts SET content=? WHERE id=?", (content, row[0]))
        db.commit()
        print(f"updated id={row[0]} {name}: {row[1]} -> {len(content)} chars")
    else:
        memory.add_fact(category=CATEGORY, content=content, source_name=name, title=title)
        nid = db.execute(
            "SELECT id FROM facts WHERE source_name=? AND category=? AND status='active'",
            (name, CATEGORY),
        ).fetchone()
        print(f"CREATED id={nid[0] if nid else '?'} {name}: {len(content)} chars")

for office in ["Marketing", "BusinessOps", "Legal", "CIO", "Creative", "Taliyah", "MovieDirector"]:
    brain = memory.brain_context_block(office)
    hits = sum(1 for name, _ in FILES if name[:-3] in brain)
    print(f"{office:<14} sees {hits}/{len(FILES)}")
