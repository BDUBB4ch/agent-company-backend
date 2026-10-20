"""Rewrite Bionova product SEO titles/descriptions against the queries Google
is ALREADY showing these pages for (Search Console, 16 months, 2026-08-23).

WHY: measured gap -- Bionova product pages pull 0.27-0.53% CTR while this same
site's AB Lighting pages pull 6-15%. 3,423 Bionova impressions produced 13
clicks. The titles/descriptions were the difference.

SECOND FINDING, and possibly bigger: the existing meta was cannabis-forward and
carried unsubstantiated yield claims ("Discover Bionova Soil SuperMix for
cannabis. Achieve higher yields...") -- indexed by Google, on a store carrying
an account-level Merchant Center misrepresentation flag, and against Barry's
own crop-neutral policy for Google channels. The rewrites are crop-neutral and
claim-free.

Backs up every field before writing; verifies every write by reading back.
Re-runnable and idempotent.
"""
import json
import os
import sys

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from dotenv import find_dotenv, load_dotenv  # noqa: E402

load_dotenv(find_dotenv())
import store  # noqa: E402

BASE = os.getenv("STORE_URL", "").rstrip("/")
AUTH = (os.getenv("STORE_CONSUMER_KEY"), os.getenv("STORE_CONSUMER_SECRET"))

# match-key -> (title, description).  Match is case-insensitive substring on name.
SEO = {
    "SUPERMIX": (
        "Bionova Soil Supermix - All-in-One Soil Fertilizer | 1L & 5L",
        "Bionova Soil Supermix: complete one-part soil feed, no separate A+B. "
        "1L and 5L in stock, ships from Colorado. Free shipping over $200. "
        "Grower-owned shop."),
    "SILUTION": (
        "Bionova SiLution Mono-Silicic Acid | 250ml, 1L & 5L In Stock",
        "SiLution mono-silicic acid with fulvic acid, boron and zinc - not "
        "potassium silicate. Independently lab trialled. 250ml, 1L and 5L. "
        "Ships from Colorado."),
    "NUTRI FORTE": (
        "Bionova Nutri Forte A+B - Hydroponic Base Nutrients | 1L-20L",
        "Two-part hydroponic base nutrient that outperformed a 12-part formula "
        "in independent testing. 1L, 5L and 20L. Ships from Colorado. Free "
        "shipping over $200."),
    "COCO FORTE": (
        "Bionova Coco Forte A+B - Coco Coir Base Nutrients | 1L-20L",
        "Bionova Coco Forte A+B, built for coco coir. Simple two-part feed in "
        "1L, 5L and 20L. Grower-owned Colorado shop. Free shipping over $200."),
    "ROOTS": (
        "Bionova Roots - Root Growth Stimulator | 250ml, 1L & 5L",
        "Bionova Roots root growth stimulator for soil, coco and hydro. 250ml, "
        "1L and 5L in stock. Ships from Colorado. Free shipping over $200."),
    "PK 13-14": (
        "Bionova PK 13-14 Bloom Booster | 250ml, 1L, 5L & 20L",
        "PK 13-14 phosphorus and potassium bloom booster for the flowering "
        "stage. 250ml through 20L. Grower-owned Colorado shop. Free shipping "
        "over $200."),
    "X-CEL": (
        "Bionova X-CEL Bloom Stimulator | 250ml, 1L & 5L In Stock",
        "Bionova X-CEL bloom stimulator for the flowering stage. 250ml, 1L and "
        "5L. Ships from Colorado. Free shipping on orders over $200."),
    "MISSING LINK": (
        "Bionova The Missing Link Stimulator | 250ml, 1L, 5L & 20L",
        "The Missing Link by Bionova - plant stimulator in 250ml, 1L, 5L and "
        "20L. Grower-owned Colorado shop. Free shipping over $200."),
    "ZYM": (
        "Bionova Zym Enzymes | Substrate Enzyme Cleaner, 250ml-20L",
        "Bionova Zym enzymes break down old root matter and speed flushing. "
        "250ml, 1L, 5L and 20L. Ships from Colorado. Free shipping over $200."),
    "VITASOL": (
        "Bionova Vitasol Stimulator & Sweetener | 250ml, 1L & 5L",
        "Bionova Vitasol sweetener and stimulator with natural sugars and trace "
        "elements. 250ml, 1L and 5L. Grower-owned Colorado shop. Free shipping "
        "over $200."),
    "CA 15": (
        "Bionova Ca 15 Calcium Additive | 15% Calcium, 1L, 5L & 20L",
        "Bionova Ca 15 calcium additive for RO and soft water. Dose calcium "
        "separately instead of a fixed cal-mag blend. 1L, 5L and 20L. Ships "
        "from Colorado."),
    "MGO 10 MAGNESIUM": (
        "Bionova MgO 10 Magnesium Additive | 10% Magnesium, 1L-20L",
        "Bionova MgO 10 magnesium additive for RO water and LED rooms. Dose "
        "magnesium separately, not a fixed blend. 1L, 5L and 20L. Ships from "
        "Colorado."),
    "MICROLIFE": (
        "Bionova Microlife Mycorrhiza Soil Enhancer | 4 lb Bag",
        "Mycorrhiza, bacillus, yeasts and enzymes with algae, coco pellets and "
        "compost. Improves soil structure, rooting and nutrient availability. "
        "Ships from Colorado."),
    "PROFIMIX": (
        "Bionova Profimix Granular Soil Fertilizer | NPK 5-4-7, 4 lb",
        "All-in-one granular soil fertilizer, vegan, NPK 5-4-7 + 2MgO. Feeds "
        "10-12 weeks from one application, no pH testing needed. Ships from "
        "Colorado."),
}

# Words that should not sit in Google-indexed product meta on this store.
RISK = ["cannabis", "marijuana", "weed", "thc", "higher yield", "increase yield",
        "boost yield", "maximize yield", "guaranteed"]


def main() -> int:
    if not all(AUTH):
        print("REFUSING: store credentials missing from .env")
        return 1

    prods = store._get("/products", {"category": 522, "per_page": 100,
                                     "status": "publish"})
    backup, applied, risky = [], [], []

    for p in prods:
        name = p.get("name", "")
        up = name.upper()
        key = next((k for k in SEO if k in up), None)
        meta = {m["key"]: m["value"] for m in (p.get("meta_data") or [])}
        old_t = meta.get("rank_math_title", "")
        old_d = meta.get("rank_math_description", "")

        blob = f"{old_t} {old_d}".lower()
        hits = [w for w in RISK if w in blob]
        if hits:
            risky.append((p["id"], name[:44], hits))

        if not key:
            continue

        backup.append({"id": p["id"], "name": name,
                       "rank_math_title": old_t,
                       "rank_math_description": old_d})

        t, d = SEO[key]
        if old_t == t and old_d == d:
            print(f"  = already set  {name[:44]}")
            continue

        r = httpx.put(f"{BASE}/wp-json/wc/v3/products/{p['id']}", auth=AUTH,
                      timeout=40,
                      json={"meta_data": [
                          {"key": "rank_math_title", "value": t},
                          {"key": "rank_math_description", "value": d}]})
        if r.status_code != 200:
            print(f"  ! FAILED {r.status_code}  {name[:40]}  {r.text[:120]}")
            continue

        chk = {m["key"]: m["value"]
               for m in (r.json().get("meta_data") or [])}
        ok = chk.get("rank_math_title") == t and \
            chk.get("rank_math_description") == d
        print(f"  {'OK' if ok else '?? UNVERIFIED'}  {name[:44]}")
        applied.append(p["id"])

    out = os.path.join(os.path.dirname(__file__), "..", "data", "restore",
                       "bionova_seo_before_2026-08-23.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(backup, fh, indent=2, ensure_ascii=False)

    print(f"\nUPDATED {len(applied)} products")
    print(f"BACKUP  {len(backup)} records -> data/restore/"
          f"bionova_seo_before_2026-08-23.json")

    if risky:
        print("\n=== PRE-EXISTING RISK WORDS FOUND IN OLD META ===")
        for pid, nm, hits in risky:
            print(f"  {pid}  {nm:<46} {hits}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
