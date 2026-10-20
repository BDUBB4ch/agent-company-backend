"""
Export a Google Merchant Center product feed (manual file upload format).

DIFFERENT JOB FROM export_products_csv.py. That one is a human-readable
spreadsheet. This one uses Google's exact required column names -- Merchant
Center rejects anything else with "Invalid or missing required attribute: id".

WHAT GOOGLE REQUIRES (and why each choice here was made):
  id             unique, <=50 chars. WooCommerce product/variation ID.
  title          <=150 chars, HTML entities decoded.
  description    <=5000 chars, HTML stripped.
  link           the product page. For a variation, its own variant URL.
  image_link     required. A product with no image CANNOT be submitted.
  availability   in_stock | out_of_stock | backorder (Woo's words differ).
  price          REGULAR price + currency. The discount goes in sale_price,
                 NOT in price -- putting the sale price in `price` is one of
                 the ways a feed earns a misrepresentation flag.
  condition      new, for everything in this catalog.
  brand + mpn    Google wants brand + an identifier. Where a product has
                 neither, identifier_exists is set to "no" -- that is the
                 honest declaration, not a workaround.
  item_group_id  ties variations of one product together.

VARIABLE PRODUCTS: the parent row is deliberately EXCLUDED. A variable parent
is not purchasable and has a price RANGE, so submitting it advertises a price
nobody can pay. Only the real variations go in, tied by item_group_id.

DRAFTS ARE EXCLUDED. Published only.

Read-only -- store._get() is the only request path.

Usage:
    ../venv/Scripts/python.exe scripts/export_google_feed.py
"""
import csv
import html
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

import store  # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
OUT_PATH = os.path.join(OUT_DIR, f"google-feed-{time.strftime('%Y-%m-%d')}.csv")

CURRENCY = "USD"
# Flat rate is $10, free over $200 (set 2026-08-14). A per-item shipping
# attribute cannot express a cart-total threshold, so this states the flat
# rate only. If Merchant Center's own shipping settings already cover this,
# delete the shipping column rather than letting the two disagree.
SHIPPING = f"US:::10.00 {CURRENCY}"

COLUMNS = [
    "id", "item_group_id", "title", "description", "link", "image_link",
    "additional_image_link", "availability", "price", "sale_price",
    "brand", "mpn", "identifier_exists", "condition", "product_type",
    "shipping",
]

AVAILABILITY = {
    "instock": "in_stock",
    "outofstock": "out_of_stock",
    "onbackorder": "backorder",
}

# Terms that would put a Google-facing listing outside the crop-neutral policy.
# These are REPORTED, never auto-edited -- product copy is Barry's call.
#
# NOTE: "bud" is deliberately NOT in this list. It was, on the first run, and
# it produced 6 false positives -- every one was ordinary horticulture
# ("flower/bud formation", "bud development"), which is exactly the
# crop-neutral language the policy WANTS. A checker that cries wolf on the
# correct wording trains you to ignore it.
CROP_TERMS = re.compile(
    r"\b(cannabis|marijuana|weed|THC|CBD|hemp|cannabinoid|dispensary)\b",
    re.I,
)


def clean_text(raw, limit):
    """Strip HTML, decode entities, collapse whitespace, truncate."""
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(html.unescape(text))  # twice: some titles are double-encoded
    text = text.replace(" ", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit].strip()


def money(value):
    try:
        return f"{float(value):.2f} {CURRENCY}"
    except (TypeError, ValueError):
        return ""


def fetch_all(path, params=None):
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


def brand_of(product):
    for b in (product.get("brands") or []):
        name = clean_text(b.get("name"), 70)
        if name:
            return name
    return ""


def build_row(pid, title, description, link, images, availability_raw,
              regular, sale, brand, sku, product_type, item_group_id=""):
    image_link = images[0] if images else ""
    extra = ",".join(images[1:11]) if len(images) > 1 else ""

    # Google's rule: declare identifier_exists=no when there is genuinely no
    # brand+identifier pair, rather than inventing an MPN.
    has_ids = bool(brand and sku)

    return {
        "id": str(pid),
        "item_group_id": str(item_group_id) if item_group_id else "",
        "title": title,
        "description": description,
        "link": link,
        "image_link": image_link,
        "additional_image_link": extra,
        "availability": AVAILABILITY.get(availability_raw, "in_stock"),
        "price": money(regular),
        "sale_price": money(sale) if sale else "",
        "brand": brand,
        "mpn": sku,
        "identifier_exists": "yes" if has_ids else "no",
        "condition": "new",
        "product_type": product_type,
        "shipping": SHIPPING,
    }


def main():
    if not store.is_configured():
        print("Store keys are not set in .env -- nothing to export.")
        return 1

    print(f"Pulling published products from {store.STORE_URL} ...")
    products = fetch_all("/products", {"status": "publish", "orderby": "title", "order": "asc"})
    print(f"  {len(products)} published products")

    rows = []
    skipped_no_image = []
    skipped_no_price = []
    crop_flagged = []

    for p in products:
        name = clean_text(p.get("name"), 150)
        desc = clean_text(p.get("description") or p.get("short_description"), 5000)
        brand = brand_of(p)
        ptype = " > ".join(clean_text(c.get("name"), 60) for c in (p.get("categories") or []))
        parent_images = [i.get("src", "") for i in (p.get("images") or []) if i.get("src")]

        if CROP_TERMS.search(f"{name} {desc}"):
            crop_flagged.append(name)

        if p.get("type") == "variable":
            # Parent deliberately excluded -- not purchasable, price is a range.
            variations = fetch_all(f"/products/{p['id']}/variations", {"status": "publish"})
            print(f"  {name}: {len(variations)} variations")
            for v in variations:
                opts = " / ".join(
                    clean_text(a.get("option"), 40) for a in (v.get("attributes") or [])
                    if a.get("option")
                )
                vtitle = clean_text(f"{name} - {opts}" if opts else name, 150)
                vimg = v.get("image") or {}
                images = ([vimg.get("src")] if vimg.get("src") else []) or parent_images
                regular = v.get("regular_price") or v.get("price")
                if not regular:
                    skipped_no_price.append(vtitle)
                    continue
                if not images:
                    skipped_no_image.append(vtitle)
                    continue
                rows.append(build_row(
                    v["id"], vtitle, desc,
                    v.get("permalink") or p.get("permalink", ""),
                    images, v.get("stock_status", "instock"),
                    regular, v.get("sale_price"), brand,
                    clean_text(v.get("sku"), 70), ptype,
                    item_group_id=p["id"],
                ))
        else:
            regular = p.get("regular_price") or p.get("price")
            if not regular:
                skipped_no_price.append(name)
                continue
            if not parent_images:
                skipped_no_image.append(name)
                continue
            rows.append(build_row(
                p["id"], name, desc, p.get("permalink", ""),
                parent_images, p.get("stock_status", "instock"),
                regular, p.get("sale_price"), brand,
                clean_text(p.get("sku"), 70), ptype,
            ))

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} feed rows")
    print(OUT_PATH)

    # Nothing is dropped silently -- a feed that quietly omits products reads
    # as "everything uploaded" when it didn't.
    if skipped_no_price:
        print(f"\nSKIPPED, no price ({len(skipped_no_price)}): "
              + "; ".join(skipped_no_price[:10]))
    if skipped_no_image:
        print(f"\nSKIPPED, no image ({len(skipped_no_image)}) "
              f"-- image_link is required by Google: "
              + "; ".join(skipped_no_image[:10]))
    if crop_flagged:
        print(f"\n[CROP POLICY] {len(set(crop_flagged))} products mention cannabis terms "
              f"in title or description. NOT edited -- your call:")
        for n in sorted(set(crop_flagged))[:20]:
            print(f"    {n}")

    no_brand = sum(1 for r in rows if not r["brand"])
    print(f"\n{no_brand} of {len(rows)} rows have no brand "
          f"(identifier_exists set to 'no' for those).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
