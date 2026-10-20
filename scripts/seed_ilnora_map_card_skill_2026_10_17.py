"""2026-10-17: seed Ilnora's cards know-how (map card + fact card) as ONE on-demand skill on her shelf
(private:ilnora, next to make-video-masterfully.md). Source: data/ilnora_cards_skill_2026_10_17.md (title line 1,
USE WHEN line 2). Supersedes the earlier map-cards.md (one home per meaning) and itself; safe to re-run.
Usage: python scripts/seed_ilnora_map_card_skill_2026_10_17.py [--dry]"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import memory  # noqa: E402

CATEGORY = "private:ilnora"
NAME = "cards.md"
OLD = ("map-cards.md",)
DRY = "--dry" in sys.argv

doc = open(os.path.join(ROOT, "data", "ilnora_cards_skill_2026_10_17.md"), encoding="utf-8").read().strip()
lines = doc.split("\n")
assert lines[1].startswith("USE WHEN:"), "line 2 is not USE WHEN"
memory.init_db()
if not DRY:
    with memory.get_db() as conn:
        for name in (NAME, *OLD):
            conn.execute("UPDATE facts SET status='superseded' WHERE category=? AND source_name=? AND status='active'",
                         (CATEGORY, name))
    memory.add_fact(CATEGORY, doc, NAME)
print(("would seed" if DRY else "seeded"), CATEGORY, NAME, len(doc), "chars |", lines[0][:60], "| superseded", OLD)
