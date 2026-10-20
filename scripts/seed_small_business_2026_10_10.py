"""Seed ONLY the four small-business knowledge files added 2026-10-10 (Barry:
"do small-business for derek and amara"). Same supersede-then-add logic as
_seed_knowledge.py, without re-seeding every other knowledge file. Safe to
re-run after editing one of the four."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import memory

FILES = {
    "marketing": ["win-back-quiet-customers.md", "growth-pulse.md", "weekly-growth-brief.md"],
    # cash-flow + inventory/restock were dropped: Amara already has
    # cash-flow-snapshot / inventory-planner / restock-decisions (2026-09-27).
    "business_ops": ["business-pulse-read.md"],
}

memory.init_db()
for domain, names in FILES.items():
    category = f"domain:{domain}"
    for name in names:
        with open(os.path.join(ROOT, "knowledge", domain, name), "r", encoding="utf-8") as f:
            content = f.read()
        with memory.get_db() as conn:
            conn.execute(
                "UPDATE facts SET status = 'superseded' WHERE category = ? AND source_name = ? AND status = 'active'",
                (category, name),
            )
        memory.add_fact(category, content, name)
        print(f"Seeded {name} -> {category}")
