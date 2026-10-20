"""2026-10-17: seed the 7 Matt Pocock skills (MIT) adapted for Sophie. Barry: "yes seed sophie's skills".
Source: data/sophie_matt_pocock_skills_draft.md, docs split by '=====' lines, title on line 1, USE WHEN on line 2.
Shelf: domain:engineering (next to her code-review / debugging docs). Supersede-and-add by source_name, so safe to re-run.
Usage: python scripts/seed_sophie_matt_pocock_skills_2026_10_17.py [--dry]"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import memory  # noqa: E402

CATEGORY = "domain:engineering"
NAMES = ["ask-before-build.md", "feedback-loop-first.md", "seams-deep-modules.md", "two-axis-review.md",
         "throwaway-prototypes.md", "retro.md", "writing-for-agents.md"]
DRY = "--dry" in sys.argv

text = open(os.path.join(ROOT, "data", "sophie_matt_pocock_skills_draft.md"), encoding="utf-8").read()
docs = [d.strip() for d in re.split(r"(?m)^=====+\s*$", text) if d.strip()]
assert len(docs) == len(NAMES), f"expected {len(NAMES)} docs, found {len(docs)}"
for name, doc in zip(NAMES, docs):
    lines = doc.split("\n")
    assert lines[1].startswith("USE WHEN:"), f"{name}: line 2 is not USE WHEN"
    assert "MIT" in lines[-1], f"{name}: last line is not the MIT credit"
memory.init_db()
for name, doc in zip(NAMES, docs):
    if not DRY:
        with memory.get_db() as conn:
            conn.execute("UPDATE facts SET status='superseded' WHERE category=? AND source_name=? AND status='active'",
                         (CATEGORY, name))
        memory.add_fact(CATEGORY, doc, name)
    print(("would seed" if DRY else "seeded"), name, len(doc), "|", doc.split("\n")[0][:70])
