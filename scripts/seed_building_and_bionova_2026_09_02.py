"""Seed two docs from the 2026-09-02 evening (Barry):
- "i need help figuring out how to get a building" ->
  knowledge/commerce/getting-a-retail-building.md -> knowledge:commerce
  (all business seats; Taliyah/Elliot excluded by the category rule)
- "they need to bionova premium fertilizer stuff too, to help people to buy it
  for their needs. minerals are food grade from bionova" ->
  knowledge/bdubb-products/bionova-line-selling-guide.md -> knowledge:bdubb_products
  (every agent, like the rest of the catalog shelf)
On-demand, USE WHEN routed. Re-runnable: same source_name supersedes.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))

import memory  # noqa: E402

DOCS = [
    ("knowledge:commerce", os.path.join(ROOT, "knowledge", "commerce", "getting-a-retail-building.md")),
    ("knowledge:bdubb_products", os.path.join(ROOT, "knowledge", "bdubb-products", "bionova-line-selling-guide.md")),
]


def title_of(text: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return (m.group(1).strip() if m else fallback)[:120]


def main() -> None:
    for category, path in DOCS:
        fn = os.path.basename(path)
        text = open(path, encoding="utf-8").read()
        first = text.splitlines()[0]
        assert first.startswith("USE WHEN:"), f"{fn}: first line is not USE WHEN"
        assert 7000 <= len(text) <= 18500, f"{fn}: {len(text)} chars -- outside 7K..18.5K"
        with memory.get_db() as conn:
            n = conn.execute("UPDATE facts SET status='superseded' WHERE category=? AND source_name=? "
                             "AND status='active'", (category, fn)).rowcount
        memory.add_fact(category, text, fn, title=title_of(text, fn[:-3]))
        assert memory._skill_use_when({"content": text}), f"{fn}: routing line did not parse"
        print(f"  {fn:<40} {len(text):>6} chars -> {category} (superseded {n})")


if __name__ == "__main__":
    main()
