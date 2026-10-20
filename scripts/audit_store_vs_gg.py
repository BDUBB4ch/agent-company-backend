"""Store-wide price audit: live WooCommerce prices vs Global Garden wholesale + SRP.

Matches by GG- SKU (exact). Variable products: compares the product's MIN price
against that SKU's wholesale/SRP row (the parent SKU maps to the base size), so
variable rows are flagged for per-variation follow-up, not auto-judged.
Output: worst offenders -- below cost, thin margin (<20%), and far under SRP.
"""
import os, re, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import store  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
txt = open(os.path.join(ROOT, "data", "bionova-evidence",
                        "global-garden-wholesale-extracted.txt"), encoding="utf-8").read()

# Parse GG rows: GG-xxxxxx<desc> <case qty> $w $srp
row_re = re.compile(r"(GG-\d{6})\s*(.+?)\s+(\d+)\s+\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})")
gg = {}
for m in row_re.finditer(txt):
    code, desc, qty, w, srp = m.groups()
    gg[code] = (desc.strip(), float(w.replace(",", "")), float(srp.replace(",", "")))
print(f"parsed {len(gg)} GG rows")

# Live store products via the read-only API
products = []
page = 1
while True:
    batch = store._get("/products", {"per_page": 100, "page": page, "status": "publish"})
    if not batch:
        break
    products.extend(batch)
    if len(batch) < 100:
        break
    page += 1
print(f"fetched {len(products)} live products\n")

below_cost, thin, under_srp, unmatched = [], [], [], []
for p in products:
    sku = (p.get("sku") or "").strip()
    price = float(p.get("price") or 0)
    if not price:
        continue
    if sku not in gg:
        if not sku.startswith("GG-"):
            unmatched.append((p["name"][:55], sku or "-", price))
        continue
    desc, w, srp = gg[sku]
    is_var = p.get("type") == "variable"
    tag = " [VARIABLE: min price vs base-size row -- check all variations]" if is_var else ""
    margin = (price - w) / price if price else 0
    line = (p["name"][:48], sku, price, w, srp, f"{margin:.0%}", tag)
    if price <= w:
        below_cost.append(line)
    elif margin < 0.20:
        thin.append(line)
    elif price < srp * 0.75:
        under_srp.append(line)

def show(title, rows):
    print(f"== {title} ({len(rows)}) ==")
    for n, sku, pr, w, srp, m, tag in sorted(rows, key=lambda r: r[2] - r[3]):
        print(f"  ${pr:>8.2f}  cost ${w:>8.2f}  SRP ${srp:>8.2f}  margin {m:>5}  {n}{tag}")
    print()

show("SELLING AT OR BELOW COST", below_cost)
show("THIN MARGIN (<20%)", thin)
show("MORE THAN 25% UNDER SRP (money on the table)", under_srp)
print(f"(unmatched non-GG-SKU products skipped: {len(unmatched)})")
