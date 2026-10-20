"""THE PLANT KNOWLEDGE THEY ACTUALLY NEED -- three docs, all nine seats.

Barry, 2026-09-18: "i want them to know the various house plants and the kind
of nutrients they may need and how what we sell could help. they need to really
know this stuff, so find the facts and give it to them, make room for all the
new knowledge. they all should know minerals and nutrients and organic etc.
make it a skil and make it concise and powerfull. it needs to be accurate as
fuck!!. also the medium the plants like to grow in. Like monstera's Aloe, etc.
even veggies and herbs."

MEASURED FIRST, per the standing rule. domain:horticulture already held 18 docs
/ 183K across all nine seats, including a houseplants doc with sections for
aroids, ficus, succulents, ferns, calathea, orchids and palms. So this is NOT
another general horticulture shelf -- the genuine gaps were:

  1. a per-plant LOOKUP dense enough to answer a real question in one hit
     (medium / light / water / feed / pH / what kills it), instead of the same
     knowledge spread over three prose docs;
  2. the BRIDGE to what B Dubb actually sells, which existed only as a 3.8K
     bionova-and-recommendations doc written before most of the catalogue;
  3. an honest statement of WHERE THE PUBLISHED RECORD STOPS.

(3) is the "accurate as fuck" part and it is the most valuable thing here.
The research found that per-species light and pH figures largely DO NOT EXIST
for houseplants -- extension publishes bands, not per-plant numbers, and only
African violet and Phalaenopsis have real published figures. Without that
stated plainly, a model asked "what PPFD does a monstera want" will produce a
confident number, and it will be invented. Every such gap is marked in the docs
and the seeder refuses to seed a doc that has lost its warnings.

ROOM: these are on-demand facts, so they cost nothing until recalled -- always-on
load per seat is 12-38K against a 140K warn line and does not move. The real
constraint is that recall injects WHOLE docs, max 3, against a 20K budget, so
each doc is kept under 18.5K and the three are split so a plant question can
pull the plant lookup AND the product map together.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "backend"))

import memory   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SLUG_MAX = 60          # memory/ingest slug ceiling -- routing words get cut past this
RECALL_LIMIT = 18_500  # recall injects whole docs against a 20K budget

# (category, source_name, path). source_name carries the word-forms Barry and
# customers actually type -- recall scores the title at 6x and does NO stemming,
# so "plants" and "plant" are different tokens and both have to be present.
DOCS = [
    ("domain:horticulture",
     "houseplants-houseplant-monstera-aloe-pothos-ficus-orchid.md",
     os.path.join(ROOT, "knowledge", "horticulture",
                  "houseplants-what-they-need.md")),
    ("domain:horticulture",
     "herbs-veg-basil-mint-tomato-lettuce-indoors-edible.md",
     os.path.join(ROOT, "knowledge", "horticulture",
                  "edibles-indoors-what-they-need.md")),
    ("domain:horticulture",
     "nutrients-nutrient-minerals-npk-deficiency-ph-ec-organic.md",
     os.path.join(ROOT, "knowledge", "horticulture",
                  "nutrients-minerals-and-organics.md")),
    ("knowledge:bdubb_products",
     "which-product-for-which-job-bionova-deficiency-fix.md",
     os.path.join(ROOT, "knowledge", "bdubb-products",
                  "which-product-for-which-job.md")),
]

# The plant lookup was ONE doc and had to be split. Measured: at 17.9K it ate
# 18.4K of recall's 20K budget, so "what should I feed my monstera" pulled the
# plant doc and NOTHING ELSE -- the product map, which is the "how what we
# sell could help" half Barry asked for, could not fit beside it. Split in two,
# either half now rides WITH the product map.
RETIRED = ("plants-plant-houseplants-monstera-aloe-herbs-veg-medium.md",)

# A doc that has lost these has lost the thing that makes it safe to use.
MUST_KEEP = {
    "houseplants-houseplant-monstera-aloe-pothos-ficus-orchid.md": [
        "DO NOT EXIST in the published record",
        "Unverified",
        "fluoride",
        "leaching",
    ],
    "herbs-veg-basil-mint-tomato-lettuce-indoors-edible.md": [
        "BLOSSOM END ROT IS A CALCIUM TRANSPORT",
        "TIPBURN IS NOT A CALCIUM SHORTAGE",
        "unverified",
    ],
    "nutrients-nutrient-minerals-npk-deficiency-ph-ec-organic.md": [
        "MOBILITY decides WHERE",
        "NEVER COMPARE AN EC NUMBER ACROSS METHODS",
        "no leaching fraction",
        "nobody has published that",
    ],
    "which-product-for-which-job-bionova-deficiency-fix.md": [
        "OUT OF STOCK",
        "not a houseplant chart",
        "lookup_product before",
    ],
}


def main() -> None:
    with memory.get_db() as conn:
        for name in RETIRED:
            cur = conn.execute("UPDATE facts SET status='superseded' "
                               "WHERE source_name = ? AND status='active'", (name,))
            if cur.rowcount:
                print(f"retired the combined doc {name}")

    for category, source, path in DOCS:
        text = open(path, encoding="utf-8").read()
        assert text.startswith("USE WHEN:"), f"{source}: must open with USE WHEN:"
        first = text.splitlines()[0]
        assert len(text) < RECALL_LIMIT, (
            f"{source}: {len(text):,} chars -- over the {RECALL_LIMIT:,} recall "
            "budget, so recall would NAME it and never inject it")
        assert len(source) - 3 <= SLUG_MAX, f"{source}: slug too long, will truncate"
        for phrase in MUST_KEEP[source]:
            assert phrase in text, f"{source}: lost its guard phrase {phrase!r}"

        # supersede any previous copy, then store fresh (never two live copies)
        with memory.get_db() as conn:
            conn.execute("UPDATE facts SET status='superseded' "
                         "WHERE source_name = ? AND status='active'", (source,))
        memory.add_fact(category=category, content=text, source_name=source,
                        title=source[:-3].replace("-", " "))

        facts = memory.get_active_facts_for_agent("Marketing")
        fact = next((f for f in facts if f["source_name"] == source), None)
        assert fact, f"{source}: not on the shelf after storing"
        read = memory._skill_use_when(fact, 1200) or ""
        want = first[len("USE WHEN:"):].strip().rstrip(".")
        assert read.rstrip(".").startswith(want[:110]), (
            f"{source}: routing line truncated.\n  want {want[:130]!r}\n"
            f"  read {read[:130]!r}")
        print(f"{category:26} {len(text):6,} chars  {source}")

    # every seat, including Taliyah and Elliot -- his words: "they all should
    # know minerals and nutrients and organic etc."
    print()
    for office in ("CIO", "Operations", "BusinessOps", "Legal", "Marketing",
                   "Creative", "MovieDirector", "Engineer", "Taliyah"):
        names = {f["source_name"] for f in memory.get_active_facts_for_agent(office)}
        have = sum(1 for _, s, _ in DOCS if s in names)
        print(f"  {office:14} has {have}/4")


if __name__ == "__main__":
    main()
