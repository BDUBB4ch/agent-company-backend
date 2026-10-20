"""Assign product_brand terms to every published product that lacks one.

WHY: Search Console reports 19 valid Merchant listings out of ~119 published
products. Google needs a brand (plus MPN/SKU) or a GTIN to produce a valid
merchant listing -- 75 products carried no brand at all, so they cannot appear
in free Shopping results no matter how good the page is.

Brand is inferred from the product's own name, which on this catalogue always
leads with the manufacturer. Anything that does not match a rule is left alone
and reported, never guessed.

Backs up every product's existing brand assignment first. Re-runnable.
"""
import json
import os
import re
import sys

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from dotenv import find_dotenv, load_dotenv  # noqa: E402

load_dotenv(find_dotenv())
import store  # noqa: E402

BASE = os.getenv("STORE_URL", "").rstrip("/")
AUTH = (os.getenv("STORE_CONSUMER_KEY"), os.getenv("STORE_CONSUMER_SECRET"))

# regex on the product name -> canonical brand name
RULES = [
    (r"\bhm\s*digital\b",            "HM Digital"),
    (r"\bgrowmax\b",                 "GrowMax Water"),
    (r"\bab\s*lighting\b",           "AB Lighting"),
    (r"\bredirooted?\b",             "Rediroot"),
    (r"\bdimlux\b",                  "Dimlux"),
    (r"\bhighdrogro\w*\b|\bhdg\d",   "HighDroGro"),
    (r"grower.s\s*ally",             "Grower's Ally"),
    (r"gard.nclean",                 "Gard'nClean"),
    (r"\bazapro\b",                  "Azapro"),
    (r"\borganitek\b",               "Organitek"),
    (r"\bblv\b",                     "BLV"),
    (r"\bbionova\b",                 "Bionova"),
    (r"\bemerald\s*harvest\b",       "Emerald Harvest"),
    (r"\bmammoth\b",                 "Mammoth"),
    (r"greenhouse\s*feeding",        "Greenhouse Feeding"),
]


def all_products():
    out, page = [], 1
    while True:
        r = store._get("/products", {"per_page": 100, "page": page,
                                     "status": "publish"})
        if not isinstance(r, list) or not r:
            break
        out += r
        page += 1
        if page > 5:
            break
    return out


def main() -> int:
    if not all(AUTH):
        print("REFUSING: store credentials missing")
        return 1

    terms = store._get("/products/brands", {"per_page": 100})
    by_name = {t["name"].strip().lower(): t["id"] for t in terms}

    prods = all_products()
    backup = [{"id": p["id"], "name": p["name"],
               "brands": [{"id": b["id"], "name": b["name"]}
                          for b in (p.get("brands") or [])]}
              for p in prods]
    out = os.path.join(os.path.dirname(__file__), "..", "data", "restore",
                       "product_brands_before_2026-08-23.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(backup, fh, indent=2, ensure_ascii=False)
    print(f"backed up {len(backup)} products -> data/restore/"
          f"product_brands_before_2026-08-23.json\n")

    created, assigned, skipped = [], 0, []

    for p in prods:
        if p.get("brands"):
            continue
        name = p.get("name", "")
        low = re.sub(r"[‘’]", "'", name).lower()
        brand = next((b for pat, b in RULES if re.search(pat, low)), None)
        if not brand:
            skipped.append((p["id"], name[:52]))
            continue

        tid = by_name.get(brand.lower())
        if tid is None:
            r = httpx.post(f"{BASE}/wp-json/wc/v3/products/brands", auth=AUTH,
                           timeout=40, json={"name": brand})
            if r.status_code not in (200, 201):
                print(f"  ! could not create brand {brand}: {r.text[:120]}")
                continue
            tid = r.json()["id"]
            by_name[brand.lower()] = tid
            created.append(f"{brand} (id {tid})")
            print(f"  + created brand term: {brand} -> id {tid}")

        r = httpx.put(f"{BASE}/wp-json/wc/v3/products/{p['id']}", auth=AUTH,
                      timeout=40, json={"brands": [{"id": tid}]})
        got = [b["name"] for b in (r.json().get("brands") or [])]
        ok = r.status_code == 200 and got
        print(f"  {'OK ' if ok else '!! '}{name[:48]:<48} -> {brand}")
        if ok:
            assigned += 1

    print(f"\nASSIGNED {assigned} products")
    if created:
        print("CREATED brand terms: " + ", ".join(created))
    if skipped:
        print(f"\nLEFT ALONE ({len(skipped)}) -- no brand in the name, "
              f"not guessed:")
        for pid, nm in skipped:
            print(f"  {pid}  {nm}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
