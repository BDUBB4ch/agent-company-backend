"""Build the full B Dubb Grows product catalog (descriptions + real image
URLs) from the site's public WooCommerce Store API into a knowledge skill."""
import html
import json
import re
import urllib.request

OUT = r"C:\Users\Owner\Desktop\AgentCompanyBackend\knowledge\product-catalog-full\SKILL.md"

def fetch(page):
    url = f"https://bdubbgrowsllc.com/wp-json/wc/store/products?per_page=100&page={page}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)

products = []
page = 1
while True:
    batch = fetch(page)
    products.extend(batch)
    if len(batch) < 100:
        break
    page += 1

def clean(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

by_cat = {}
for p in products:
    cats = p.get("categories") or [{"name": "Other"}]
    cat = cats[0]["name"]
    by_cat.setdefault(cat, []).append(p)

lines = [
    "# B Dubb Grows — FULL Product Catalog (live data with real images)",
    "",
    "Every product on bdubbgrowsllc.com with its REAL product page URL, REAL",
    "product photo URL, price, and description — pulled from the store's own",
    "database. USE THE IMAGE URL when drafting any post about a product: that",
    "is the actual product photo customers will receive, never a generated",
    "look-alike. Generated scenes are for mood/b-roll; the real photo is for",
    "the product itself.",
    "",
]
for cat in sorted(by_cat):
    lines.append(f"## {cat}")
    for p in sorted(by_cat[cat], key=lambda x: x.get("name", "")):
        name = clean(p.get("name"))
        link = p.get("permalink", "")
        imgs = p.get("images") or []
        img = imgs[0].get("src", "").split("?")[0] if imgs else ""
        prices = p.get("prices") or {}
        minor = int(prices.get("currency_minor_unit", 2))
        def money(v):
            try:
                return f"${int(v)/(10**minor):.2f}"
            except (TypeError, ValueError):
                return ""
        price = money(prices.get("price"))
        pmin, pmax = money(prices.get("price_range", {}).get("min_amount") if prices.get("price_range") else None), \
                     money(prices.get("price_range", {}).get("max_amount") if prices.get("price_range") else None)
        price_s = f"{pmin}-{pmax}" if pmin and pmax else price
        stock = "" if p.get("is_in_stock", True) else " [OUT OF STOCK]"
        desc = clean(p.get("short_description") or p.get("description"))[:220]
        lines.append(f"### {name}{stock}")
        if price_s:
            lines.append(f"- Price: {price_s}")
        lines.append(f"- Page: {link}")
        if img:
            lines.append(f"- Product photo: {img}")
        if desc:
            lines.append(f"- {desc}")
        lines.append("")

import os
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print(f"{len(products)} products across {len(by_cat)} categories -> {OUT}")
print(f"file size: {os.path.getsize(OUT)/1024:.0f} KB")
