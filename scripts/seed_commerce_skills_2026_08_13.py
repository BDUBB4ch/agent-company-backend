"""Seed the business-craft skill set (knowledge/commerce/*) into the brain.

Category knowledge:commerce -- shared, so every business-facing seat sees the
index lines; Taliyah and MovieDirector are excluded via
memory._SHARED_CATEGORY_EXCLUSIONS (edited same day). All three are .md =
ON-DEMAND: index line + read_skill, never always-on context cost.

Re-runnable: upserts by (source_name, category).
"""
import sys, os, sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import memory  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
SRC = os.path.join(ROOT, "knowledge", "commerce")
CATEGORY = "knowledge:commerce"

FILES = [
    ("business-finance-and-taxes.md", "Business finance and taxes -- margins, cash flow, quarterly estimates, nexus, deductions"),
    ("product-sourcing-and-dropshipping.md", "Product sourcing -- finding, vetting and pricing new products (Gotcho Back)"),
    ("supplier-scam-red-flags.md", "Scam and fraud red flags -- suppliers, inbound offers, payment tells"),
]

db_path = memory.DB_PATH if hasattr(memory, "DB_PATH") else os.path.join(ROOT, "data", "brain.db")
db = sqlite3.connect(db_path)

for fname, title in FILES:
    content = open(os.path.join(SRC, fname), encoding="utf-8").read()
    row = db.execute(
        "SELECT id, length(content) FROM facts WHERE source_name=? AND category=? AND status='active'",
        (fname, CATEGORY),
    ).fetchone()
    if row:
        db.execute("UPDATE facts SET content=? WHERE id=?", (content, row[0]))
        db.commit()
        print(f"updated id={row[0]} {fname}: {row[1]} -> {len(content)} chars")
    else:
        memory.add_fact(category=CATEGORY, content=content, source_name=fname, title=title)
        nid = db.execute(
            "SELECT id FROM facts WHERE source_name=? AND category=? AND status='active'",
            (fname, CATEGORY),
        ).fetchone()
        print(f"CREATED id={nid[0] if nid else '?'} {fname}: {len(content)} chars")

# Verify: visible with routing lines for Amara, absent for Taliyah/Elliot.
print()
for office in ["BusinessOps", "Marketing", "CIO", "Taliyah", "MovieDirector"]:
    brain = memory.brain_context_block(office)
    hits = [l.strip()[:110] for l in brain.splitlines()
            if any(f[0][:-3] in l for f in FILES) and l.strip().startswith("- ")]
    print(f"{office:<14} sees {len(hits)}/3 commerce skills"
          + (f"  e.g. {hits[0]}" if hits else ""))
