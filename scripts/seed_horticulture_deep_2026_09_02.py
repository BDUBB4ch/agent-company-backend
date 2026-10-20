"""Seed the deep horticulture study (2026-09-02) to the shared horticulture shelf.

Barry: "they all need to know about all plants. what minerals they need and
micro and macro nutrients. Soil or whatever grow medium they like, peat etc.
house plants and fruits and veggies. deep study on those please."

Ten one-concern reference docs in knowledge/horticulture/, each written from
extension / peer-reviewed sources with a USE WHEN routing line, land in
`domain:horticulture` -- the domain granted to all nine seats. On-demand
(`.md`), so zero always-on cost; recall serves them when a plant question
comes up. Re-runnable: a doc with the same source_name supersedes the old row,
never deletes it. Two of the July starter docs are superseded by the new set
(their content is a strict subset); the Bionova recommendation doc and the
indoor-crops/equipment doc are kept -- they carry product and gear specifics
the new set deliberately leaves out.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))

import memory  # noqa: E402

CATEGORY = "domain:horticulture"
FOLDER = os.path.join(ROOT, "knowledge", "horticulture")
NEW = [
    "macronutrients.md",
    "micronutrients.md",
    "ph-ec-and-water.md",
    "growing-media-and-systems.md",
    "vegetables-and-fruit.md",
    "houseplants.md",
    "physiology-and-environment.md",
    "diagnosing-plant-problems.md",
    "cannabis-cultivation.md",
    "soil-biology-and-organics.md",
    # 2026-09-02 evening (Barry: "all plants" -> "house plants, veggies, small
    # fruit trees and cannabis", "tropical plants as well", "microgreens and
    # all that"):
    "herbs-and-microgreens.md",
    "flowers-and-ornamentals.md",
    "trees-shrubs-and-fruit-trees.md",
    "propagation-and-seed-starting.md",
    "tropical-plants.md",
    "medicinal-herbs-and-plants.md",   # "medicinal herbs and plants too"
]
SUPERSEDED_BY_NEW = [
    "plant-nutrition-fundamentals.md",      # -> macronutrients + micronutrients
    "growing-media-soil-hydro-coco.md",     # -> growing-media-and-systems
]


def title_of(text: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return (m.group(1).strip() if m else fallback)[:120]


def main() -> None:
    total = 0
    with memory.get_db() as conn:
        for fn in NEW:
            path = os.path.join(FOLDER, fn)
            text = open(path, encoding="utf-8").read()
            first = text.splitlines()[0] if text else ""
            assert first.startswith("USE WHEN:"), f"{fn}: first line is not USE WHEN"
            assert len(text) >= 7000, f"{fn}: only {len(text)} chars -- too thin"
            # recall injects WHOLE docs against RECALL_BUDGET 20,000 and never
            # clips -- an oversize doc is named but never read.
            assert len(text) <= 18500, f"{fn}: {len(text)} chars -- over the recall budget, trim it"
            old = conn.execute(
                "SELECT id FROM facts WHERE category=? AND source_name=? AND status='active'",
                (CATEGORY, fn)).fetchall()
            for r in old:
                conn.execute("UPDATE facts SET status='superseded' WHERE id=?", (r["id"],))
            total += len(text)
            print(f"  {fn:<36} {len(text):>6} chars  (superseded {len(old)} old row(s))")
        for fn in SUPERSEDED_BY_NEW:
            n = conn.execute(
                "UPDATE facts SET status='superseded' WHERE category=? AND source_name=? "
                "AND status='active'", (CATEGORY, fn)).rowcount
            print(f"  retired {fn:<30} ({n} row)")
    # add_fact opens its own connection -- outside the block above
    for fn in NEW:
        text = open(os.path.join(FOLDER, fn), encoding="utf-8").read()
        memory.add_fact(CATEGORY, text, fn, title=title_of(text, fn[:-3]))
    print(f"seeded {len(NEW)} docs, {total:,} chars, to {CATEGORY}")
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT source_name, length(content) n FROM facts WHERE category=? "
            "AND status='active' ORDER BY source_name", (CATEGORY,)).fetchall()
    print(f"shelf now: {len(rows)} active docs, {sum(r['n'] for r in rows):,} chars")
    with memory.get_db() as conn:
        grants = [r[0] for r in conn.execute(
            "SELECT office_name FROM agent_domains WHERE domain='horticulture'")]
    print("granted to:", sorted(grants))


if __name__ == "__main__":
    main()
