"""
Export the full B Dubb Grows catalog to a CSV Barry can open in Excel or
import straight into Google Sheets.

Read-only: uses store._get() only (the single GET path in store.py), so this
cannot change anything on the live site.

Variable products get one row for the parent AND one row per variation, so
per-size prices are visible instead of a "$12.95 - $107.95" range string.

Usage:
    ../venv/Scripts/python.exe scripts/export_products_csv.py
"""
import csv
import html
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

import store  # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
OUT_PATH = os.path.join(OUT_DIR, f"bdubb-products-{time.strftime('%Y-%m-%d')}.csv")

COLUMNS = [
    "Product", "Variation", "Type", "SKU", "Status",
    "Price", "Regular Price", "Sale Price", "On Sale",
    "Stock Status", "Stock Qty", "Categories", "Brands",
    "Product URL", "Image URL", "Product ID",
]


def clean(v):
    return html.unescape(str(v or "")).strip()


def fetch_all(path, params=None):
    """Page through a WooCommerce collection until it runs dry."""
    out, page = [], 1
    while page <= 20:
        batch = store._get(path, {**(params or {}), "per_page": 100, "page": page})
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return out


def brands_for(product):
    for key in ("brands", "product_brand"):
        vals = product.get(key)
        if isinstance(vals, list) and vals:
            return ", ".join(clean(b.get("name") if isinstance(b, dict) else b) for b in vals)
    return ""


def main():
    if not store.is_configured():
        print("Store keys are not set in .env -- nothing to export.")
        return 1

    print(f"Pulling products from {store.STORE_URL} ...")
    products = fetch_all("/products", {"status": "any", "orderby": "title", "order": "asc"})
    print(f"  {len(products)} products")

    rows = []
    for p in products:
        imgs = p.get("images") or []
        base = {
            "Product": clean(p.get("name")),
            "Variation": "",
            "Type": p.get("type", ""),
            "SKU": clean(p.get("sku")),
            "Status": p.get("status", ""),
            "Price": p.get("price", ""),
            "Regular Price": p.get("regular_price", ""),
            "Sale Price": p.get("sale_price", ""),
            "On Sale": "YES" if p.get("on_sale") else "",
            "Stock Status": p.get("stock_status", ""),
            "Stock Qty": p.get("stock_quantity") if p.get("stock_quantity") is not None else "",
            "Categories": ", ".join(clean(c.get("name")) for c in (p.get("categories") or [])),
            "Brands": brands_for(p),
            "Product URL": p.get("permalink", ""),
            "Image URL": imgs[0].get("src", "") if imgs else "",
            "Product ID": p.get("id", ""),
        }
        rows.append(base)

        if p.get("type") == "variable":
            variations = fetch_all(f"/products/{p['id']}/variations", {"status": "any"})
            print(f"  {base['Product']}: {len(variations)} variations")
            for v in variations:
                vimgs = v.get("image")
                label = ", ".join(
                    f"{clean(a.get('name'))}: {clean(a.get('option'))}"
                    for a in (v.get("attributes") or [])
                ) or clean(v.get("description"))[:60]
                rows.append({
                    **base,
                    "Variation": label,
                    "Type": "variation",
                    "SKU": clean(v.get("sku")),
                    "Status": v.get("status", ""),
                    "Price": v.get("price", ""),
                    "Regular Price": v.get("regular_price", ""),
                    "Sale Price": v.get("sale_price", ""),
                    "On Sale": "YES" if v.get("on_sale") else "",
                    "Stock Status": v.get("stock_status", ""),
                    "Stock Qty": v.get("stock_quantity") if v.get("stock_quantity") is not None else "",
                    "Image URL": (vimgs or {}).get("src", "") if isinstance(vimgs, dict) else base["Image URL"],
                    "Product URL": v.get("permalink", "") or base["Product URL"],
                    "Product ID": v.get("id", ""),
                })

    os.makedirs(OUT_DIR, exist_ok=True)
    # utf-8-sig so Excel opens accented names correctly on Windows.
    with open(OUT_PATH, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    parents = sum(1 for r in rows if r["Type"] != "variation")
    print(f"\nWrote {len(rows)} rows ({parents} products + {len(rows) - parents} variations)")
    print(OUT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
