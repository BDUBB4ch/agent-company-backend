"""Reprice the GHF (Green House Feeding) line from Global Garden SRP down to
live market -- roughly a dollar under Hydrobuilder, .95 endings.

WHY: GHF was priced at exactly GG's SRP (cost x 2). Hydrobuilder runs the same
SKUs at cost x 1.33, putting Barry ~50% above a national retailer on every
size. That is why the line does not sell. Same "SRP is fiction" pattern the
2026-08-13 Emerald Harvest audit found -- EH was fixed then and is already at
market; GHF was missed.

MARGIN: this deliberately drops the line from ~50% to ~25%. GHF is a
traffic/filler line, not the profit line. Bionova is where the moat is
(40-75% under wholesale). 25% of a sale beats 50% of nothing.

PRICE BASIS, honestly recorded:
  - BioGrow, BioBloom: fetched from hydrobuilder.com product pages 2026-08-23.
  - Short Flower, Booster PK+: Hydrobuilder "from" prices (collection page).
  - Hybrids, Long Flower, Grow, Calcium: share Short Flower's exact GG cost
    ladder ($16/$25/$50/$300), so the same retail ladder is applied.
  - BioEnhancer: DELIBERATELY EXCLUDED. No cost line exists in the GG sheet,
    and this repo does not guess a price on a product it cannot cost.

Backs up every price first. Re-runnable. Restore with the JSON in data/restore.
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
BACKUP = os.path.join(os.path.dirname(__file__), "..", "data", "restore",
                      "ghf_prices_before_market_reprice_2026-08-23.json")

# size-token -> new regular price, per GHF line
LADDER_CHEAP = {"500g": "20.95", "1kg": "32.95", "2.5kg": "65.95",
                "25kg": "394.95"}          # cost 16 / 25 / 50 / 300
LADDER_PK = {"500g": "36.95", "1kg": "58.95", "2.5kg": "119.95",
             "25kg": "789.95"}             # cost 28 / 45 / 90 / 598
BIOGROW = {"500g": "36.95", "1kg": "58.95", "2.5kg": "119.95",
           "25kg": "664.95"}               # cost 28 / 45 / 90 / 499
BIOBLOOM = {"500g": "42.95", "1kg": "64.95", "2.5kg": "132.95",
            "25kg": "729.95"}              # cost 32.50 / 49 / 100 / 549

LINES = [
    ("bio line biogrow",   BIOGROW),
    ("bio line biobloom",  BIOBLOOM),
    ("booster pk",         LADDER_PK),
    ("short flower",       LADDER_CHEAP),
    ("long flower",        LADDER_CHEAP),
    ("hybrids",            LADDER_CHEAP),
    ("mineral line grow",  LADDER_CHEAP),
    ("calcium",            LADDER_CHEAP),
]
SKIP = ["bioenhancer", "bio enhancer"]


def size_key(text: str) -> str | None:
    t = text.lower().replace(" ", "")
    if "25kg" in t or "55lb" in t:
        return "25kg"
    if "2.5kg" in t or "5.5lb" in t:
        return "2.5kg"
    if "1kg" in t or "2.2lb" in t:
        return "1kg"
    if "500g" in t or "1.1lb" in t:
        return "500g"
    return None


def main() -> int:
    if not all(AUTH):
        print("REFUSING: store credentials missing")
        return 1

    prods = [p for p in store._get("/products", {"search": "GHF",
                                                 "per_page": 50,
                                                 "status": "publish"})
             if "GHF" in p.get("name", "").upper()]
    backup, changed, skipped = [], 0, []

    for p in prods:
        name = p.get("name", "")
        low = name.lower()
        if any(s in low for s in SKIP):
            skipped.append(f"{name[:44]}  (no cost data -- left alone)")
            continue
        ladder = next((l for key, l in LINES if key in low), None)
        if ladder is None:
            skipped.append(f"{name[:44]}  (no ladder matched)")
            continue

        if p.get("type") != "variable":
            skipped.append(f"{name[:44]}  (not variable)")
            continue

        for v in store._get(f"/products/{p['id']}/variations", {"per_page": 30}):
            opts = " ".join(str(a.get("option", ""))
                            for a in (v.get("attributes") or []))
            key = size_key(opts) or size_key(v.get("sku") or "")
            if not key:
                skipped.append(f"{name[:34]} / {opts[:20]}  (size unreadable)")
                continue
            new = ladder[key]
            old = v.get("regular_price")
            backup.append({"product_id": p["id"], "variation_id": v["id"],
                           "name": name, "sku": v.get("sku"), "size": key,
                           "regular_price": old,
                           "sale_price": v.get("sale_price")})
            if old == new:
                print(f"  =  {name[:34]:<34} {key:<6} already {new}")
                continue
            r = httpx.put(f"{BASE}/wp-json/wc/v3/products/{p['id']}/"
                          f"variations/{v['id']}", auth=AUTH, timeout=45,
                          json={"regular_price": new})
            ok = r.status_code == 200
            changed += ok
            print(f"  {'OK' if ok else '!!'} {name[:34]:<34} {key:<6} "
                  f"{old:>9} -> {r.json().get('regular_price')}")

    os.makedirs(os.path.dirname(BACKUP), exist_ok=True)
    with open(BACKUP, "w", encoding="utf-8") as fh:
        json.dump(backup, fh, indent=2, ensure_ascii=False)

    print(f"\nREPRICED {changed} variations")
    print(f"backed up {len(backup)} -> data/restore/"
          f"ghf_prices_before_market_reprice_2026-08-23.json")
    if skipped:
        print("\nLEFT ALONE:")
        for s in skipped:
            print("  " + s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
