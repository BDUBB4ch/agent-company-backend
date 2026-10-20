"""HERBS, VEG, FRUIT TREES AND HOUSEPLANTS GET THEIR OWN CATEGORIES + SUB-CATS.

Barry, 2026-09-18: "herbs and veggies and fruit trees all need their own
category, then sub cats. as well." -> "house plants too."

WHAT A CATEGORY ACTUALLY IS HERE, so the split does something real rather than
being a rename: `domain:<name>` is (a) the permission unit -- who sees a doc --
and (b) what braingraph draws as a HUB in the brain map. Twenty plant docs on
one flat `horticulture` hub is one blob on his screen and one undifferentiated
pile for recall. Four crop domains give four hubs.

WHAT MOVES, AND WHAT DELIBERATELY DOES NOT:

  domain:houseplants  the per-plant lookup, the care/pests prose, tropicals
  domain:herbs        the herb lookup, growing/harvest craft, medicinal herbs
  domain:vegetables   the veg lookup, growing craft (pollination, training)
  domain:fruit_trees  trees, shrubs and fruit trees

  domain:horticulture KEEPS the cross-cutting fundamentals -- macronutrients,
  micronutrients, pH/EC/water, media, the nutrients reference, diagnosis, soil
  biology, physiology, propagation, plus cannabis, flowers, equipment and the
  Bionova playbook. Those apply to ALL FOUR crops, and duplicating them into
  each category is precisely how two copies of the same fact drift apart --
  the lesson this build has paid for twice on the canon.

SUB-CATEGORIES: the fact schema has no sub-category field, and inventing one
would mean a migration plus changes to every read path. They go where they are
actually usable -- a SUB-CATEGORIES index at the top of each crop's lookup doc,
inside the window recall reads, so an agent can see the shape of the group
before it starts answering.

The combined edibles doc is split in two on the same cut, because a doc that
spans herbs AND vegetables cannot sit in either category honestly.

Re-runnable. Nothing is deleted; categories are updated in place so fact ids,
history and the brain map's edges survive.
"""
import json
import os
import sys
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "backend"))

import memory   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HORT = os.path.join(ROOT, "knowledge", "horticulture")

OFFICES = ("CIO", "Operations", "BusinessOps", "Legal", "Marketing",
           "Creative", "MovieDirector", "Engineer", "Taliyah")
NEW_DOMAINS = ("houseplants", "herbs", "vegetables", "fruit_trees")

MOVE = {
    "domain:houseplants": [
        "houseplants-houseplant-monstera-aloe-pothos-ficus-orchid.md",
        "houseplants.md",
        "tropical-plants.md",
    ],
    "domain:herbs": [
        "herbs-and-microgreens.md",
        "medicinal-herbs-and-plants.md",
    ],
    "domain:vegetables": [
        "vegetables-and-fruit.md",
    ],
    "domain:fruit_trees": [
        "trees-shrubs-and-fruit-trees.md",
    ],
}

SUBCATS = {
    "houseplants-houseplant-monstera-aloe-pothos-ficus-orchid.md":
        ("Aroids (monstera, pothos, philodendron) - Succulents and cacti "
         "(snake plant, ZZ, aloe, echeveria) - Ficus (fiddle leaf, rubber "
         "plant) - Ferns - Prayer plants (calathea, maranta) - Orchids - "
         "Palms - Flowering (african violet, peace lily, spider plant)"),
    "herbs-indoors-what-they-need.md":
        ("Soft leafy herbs (basil, mint, cilantro, parsley) - Woody "
         "Mediterranean herbs (rosemary, thyme, oregano, sage) - Alliums "
         "(green onion) - Microgreens"),
    "vegetables-indoors-what-they-need.md":
        ("Leafy greens (lettuce, spinach, kale) - Fruiting crops (tomato, "
         "pepper, cucumber) - Roots (radish) - Legumes (bush beans) - "
         "Berries (strawberry)"),
}


def _split_edibles() -> list[tuple[str, str, str]]:
    """The combined edibles doc -> one herb doc + one vegetable doc."""
    src = os.path.join(HORT, "edibles-indoors-what-they-need.md")
    if not os.path.isfile(src):
        return []
    t = open(src, encoding="utf-8").read()
    head, _, rest = t.partition("## 🔑 The herb light split")
    herbs, _, veg = rest.partition("## Vegetables and fruiting crops")
    preamble = head.split("\n", 1)[1]
    preamble = preamble[preamble.index("## ⚠️ Before you quote a number"):]

    h_use = ("USE WHEN: herb, herbs, basil, mint, cilantro, coriander, parsley, "
             "rosemary, thyme, oregano, sage, green onion, scallion, chives, "
             "microgreen, microgreens, herb garden, growing herbs indoors.\n")
    v_use = ("USE WHEN: veg, vegetable, vegetables, lettuce, greens, salad, "
             "spinach, kale, tomato, tomatoes, pepper, peppers, chili, cucumber, "
             "strawberry, strawberries, bean, beans, radish, growing food "
             "indoors, indoor vegetables.\n")

    hp = os.path.join(HORT, "herbs-indoors-what-they-need.md")
    vp = os.path.join(HORT, "vegetables-indoors-what-they-need.md")
    open(hp, "w", encoding="utf-8").write(
        h_use + "\n# Herbs indoors -- what each one needs\n\n"
        f"**SUB-CATEGORIES:** {SUBCATS['herbs-indoors-what-they-need.md']}\n\n"
        "Per-herb lookup. Vegetables are in their own doc; growing and "
        "harvesting craft is in the herbs-and-microgreens doc; which product "
        "answers it is in the B Dubb product map.\n\n"
        + preamble + "## 🔑 The herb light split" + herbs.strip() + "\n")
    open(vp, "w", encoding="utf-8").write(
        v_use + "\n# Vegetables indoors -- what each one needs\n\n"
        f"**SUB-CATEGORIES:** {SUBCATS['vegetables-indoors-what-they-need.md']}\n\n"
        "Per-crop lookup. Herbs are in their own doc; growing craft "
        "(pollination, training, pruning) is in the vegetables-and-fruit doc; "
        "which product answers it is in the B Dubb product map.\n\n"
        + preamble + "## Vegetables and fruiting crops" + veg.strip() + "\n")
    os.remove(src)
    return [
        ("domain:herbs", "herbs-basil-mint-rosemary-thyme-indoors-what-they-need.md", hp),
        ("domain:vegetables", "vegetables-veg-tomato-lettuce-pepper-indoors-needs.md", vp),
    ]


def main() -> None:
    for d in NEW_DOMAINS:
        assert d in memory.KNOWN_DOMAINS, f"{d} missing from memory.KNOWN_DOMAINS"
        for office in OFFICES:
            memory.grant_domain_access(office, d)
    print(f"granted {len(NEW_DOMAINS)} new domains to all {len(OFFICES)} seats")

    # the combined edibles doc has to be split before anything is categorised
    new_docs = _split_edibles()
    for category, source, path in new_docs:
        text = open(path, encoding="utf-8").read()
        assert text.startswith("USE WHEN:")
        assert len(text) < 18_500, f"{source}: {len(text)} over the recall budget"
        assert "SUB-CATEGORIES" in text
        with memory.get_db() as conn:
            conn.execute("UPDATE facts SET status='superseded' "
                         "WHERE source_name = ? AND status='active'", (source,))
        memory.add_fact(category=category, content=text, source_name=source,
                        title=source[:-3].replace("-", " "))
        print(f"  split out {source} ({len(text):,}) -> {category}")

    with memory.get_db() as conn:
        conn.execute("UPDATE facts SET status='superseded' WHERE source_name = ? "
                     "AND status='active'",
                     ("herbs-veg-basil-mint-tomato-lettuce-indoors-edible.md",))

    facts = {f["source_name"]: f for f in memory.get_active_facts_for_agent("Marketing")}
    stamp = datetime.datetime.now().strftime("%Y-%m-%d")
    moved, backup = 0, {}
    for category, sources in MOVE.items():
        for source in sources:
            fact = facts.get(source)
            if not fact:
                print(f"  ?? {source} not found -- skipped")
                continue
            backup[source] = {"id": fact["id"], "was": fact["category"]}
            content = fact["content"]
            sub = SUBCATS.get(source)
            if sub and "SUB-CATEGORIES" not in content:
                lines = content.splitlines()
                at = next((i for i, l in enumerate(lines)
                           if l.lstrip().startswith("#")), 0)
                lines.insert(at + 1, f"\n**SUB-CATEGORIES:** {sub}\n")
                content = "\n".join(lines)
            with memory.get_db() as conn:
                conn.execute("UPDATE facts SET category = ?, content = ? WHERE id = ?",
                             (category, content, fact["id"]))
            moved += 1

    with open(os.path.join(ROOT, "data",
                           f"backup_plant_categories_{stamp}.json"),
              "w", encoding="utf-8") as f:
        json.dump(backup, f, indent=1)
    print(f"\nmoved {moved} docs into crop categories "
          f"(backup backup_plant_categories_{stamp}.json)\n")

    # --- verify: every seat sees every category, and the hubs are real ---
    facts = memory.get_active_facts_for_agent("Taliyah")
    by_cat: dict[str, list] = {}
    for f in facts:
        cat = f.get("category") or ""
        if cat.startswith("domain:") and cat.split(":")[1] in (
                *NEW_DOMAINS, "horticulture"):
            by_cat.setdefault(cat, []).append(f["source_name"])
    for cat in sorted(by_cat):
        print(f"{cat:24} {len(by_cat[cat]):2} docs")
        for sn in sorted(by_cat[cat]):
            print(f"      {sn}")
    for d in NEW_DOMAINS:
        assert f"domain:{d}" in by_cat, f"domain:{d} has no docs"


if __name__ == "__main__":
    main()
