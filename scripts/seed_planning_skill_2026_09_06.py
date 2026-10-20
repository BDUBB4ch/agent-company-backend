"""Seed knowledge/engineering/planning-before-building.md to Sophie's
domain:engineering shelf (on-demand, USE WHEN routed). Re-runnable: same
source_name supersedes the old row. Barry, 2026-09-06: "she needs the
planning ability and deep thinking, before she builds anything."
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))

import memory  # noqa: E402

CATEGORY = "domain:engineering"
FN = "planning-before-building.md"
path = os.path.join(ROOT, "knowledge", "engineering", FN)
text = open(path, encoding="utf-8").read()
assert text.startswith("USE WHEN:"), "first line must be USE WHEN"
assert len(text) <= 18500, "over the recall budget"
m = re.search(r"^#\s+(.+)$", text, re.M)
title = (m.group(1).strip() if m else FN[:-3])[:120]
with memory.get_db() as conn:
    n = conn.execute("UPDATE facts SET status='superseded' WHERE category=? AND source_name=? AND status='active'",
                     (CATEGORY, FN)).rowcount
memory.add_fact(CATEGORY, text, FN, title=title)
with memory.get_db() as conn:
    row = conn.execute("SELECT id, length(content) n FROM facts WHERE category=? AND source_name=? AND status='active'",
                       (CATEGORY, FN)).fetchone()
print(f"seeded {FN} as fact {row['id']} ({row['n']} chars), superseded {n}; routing: {memory._skill_use_when({'content': text})[:80]!r}")
