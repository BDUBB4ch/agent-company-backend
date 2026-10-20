"""Build knowledge/bdubb-products/global-garden-wholesale-pricelist.md from the
extracted text, then it gets seeded by seed_bionova_lab_results_2026_08_13.py.

Big on-demand skill (same pattern as product-catalog-full): full data inline,
because agents other than Sophie cannot read arbitrary disk files -- read_skill
is their only retrieval path.
"""
import os

ROOT = os.path.join(os.path.dirname(__file__), "..")
raw = open(os.path.join(ROOT, "data", "bionova-evidence",
                        "global-garden-wholesale-extracted.txt"), encoding="utf-8").read()

INTRO = """# Global Garden wholesale price list (2025-09-30) — full-catalog COGS + SRP (INTERNAL)

USE WHEN: any margin, pricing or cost question about NON-Bionova products (tents, lights, meters, Emerald Harvest, pesticides, RO, etc.), any store-wide repricing work, or the brick-and-mortar breakeven analysis. Bionova costs live in bionova-cost-basis instead.

⚠️ **INTERNAL AND CONFIDENTIAL** -- the source document is marked confidential by
Global Garden (Barry's active supplier for everything except Bionova). Costs, the
supplier's terms and this list NEVER appear in anything outbound. Margins as
percentages may be discussed with Barry only.

HOW TO READ THE DATA BELOW: rows are `[Item Code][Description] [Case Qty]
[Wholesale each] [SRP]`. **SRP is the supplier's suggested retail -- the reference
price the market expects.** Margin at SRP = (SRP - wholesale) / SRP, typically
40-45% on this list. Barry pays regular wholesale (no extra discount, unlike his
40%-under Bionova deal with Winter).

⚠️ **THE FINDING THAT PROMPTED THIS (2026-08-13): the store appears to be selling
some items AT OR BELOW ITS OWN WHOLESALE COST.** Live check: EH Cali Pro Grow A
quart is $8.25 wholesale / $17.00 SRP on this list -- the store's live price for
Cali Pro was $8.00. Same wrong-anchor disease as the Bionova line (see
bionova-wholesale-pricelist Finding 1). Before ANY promo or bundle recommendation
on a non-Bionova product: look up its live price with lookup_product, find it in
this list, and CHECK THE MARGIN IS REAL. A store-wide price-vs-SRP audit is the
obvious Amara project; surface per-product math, Barry decides.

Source PDF archived: data/bionova-evidence/global-garden-wholesale-2025-09-30.pdf
(25 pages; this is the machine-extracted text, spot-check the PDF if a number reads
oddly). GG item codes (GG-xxxxxx) match the store's own SKUs where set.

---

"""

out = INTRO + raw + "\n"
dest = os.path.join(ROOT, "knowledge", "bdubb-products", "global-garden-wholesale-pricelist.md")
open(dest, "w", encoding="utf-8").write(out)
print(f"wrote {dest}: {len(out)} chars")
