"""2026-10-17: seed the know-how for the new tools (plan step 3): Vivian's making-product-videos.md (private:Creative),
Sophie's text-to-cad.md + hyperframes-maintenance.md (private:Engineer). Source: data/skills_2026_10_17/*.md (title
line 1, USE WHEN line 2). Supersede-and-add by source_name; safe to re-run.
Usage: python scripts/seed_tool_skills_2026_10_17.py [--dry]"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import memory  # noqa: E402

DOCS = [("private:Creative", "making-product-videos.md"),
        ("private:Engineer", "text-to-cad.md"),
        ("private:Engineer", "hyperframes-maintenance.md")]
DRY = "--dry" in sys.argv
memory.init_db()
for category, name in DOCS:
    doc = open(os.path.join(ROOT, "data", "skills_2026_10_17", name), encoding="utf-8").read().strip()
    lines = doc.split("\n")
    assert lines[1].startswith("USE WHEN:"), f"{name}: line 2 is not USE WHEN"
    if not DRY:
        with memory.get_db() as conn:
            conn.execute("UPDATE facts SET status='superseded' WHERE category=? AND source_name=? AND status='active'",
                         (category, name))
        memory.add_fact(category, doc, name)
    print(("would seed" if DRY else "seeded"), category, name, len(doc), "chars |", lines[0][:60])
