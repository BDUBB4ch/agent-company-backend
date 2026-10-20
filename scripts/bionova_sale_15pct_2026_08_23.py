"""Put a time-boxed 15% sale on the Bionova line (category 522).

WHY: the homepage "ON SALE NOW / Current Deals" row is a live on-sale query
(`[ux_products show="onsale"]`) and every GHF sale price had been cleared, so
it was rendering empty. Barry also has ~$6,000 of Bionova stock with roughly
3% sold, so a real discount serves two purposes at once.

⚠️ END DATE IS THE POINT. The old GHF sale carried NO date_on_sale_to, which
is how it became a permanent "sale" whose original price nothing ever sold at
-- a reference-price problem. This one expires on its own.

STACKING: not an issue here -- Barry confirmed 2026-08-23 that BIG15/BIG10
already have "Exclude sale items" set on the coupons, so a sale price and a
welcome code cannot combine. If that setting is ever turned off, redo the
margin math before running this: 15% sale + BIG15 lands around 28% off.

Backs up every price before writing. Re-runnable; clears with --clear.
"""
import json
import os
import sys
from decimal import ROUND_DOWN, Decimal

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from dotenv import find_dotenv, load_dotenv  # noqa: E402

load_dotenv(find_dotenv())
import store  # noqa: E402

BASE = os.getenv("STORE_URL", "").rstrip("/")
AUTH = (os.getenv("STORE_CONSUMER_KEY"), os.getenv("STORE_CONSUMER_SECRET"))

DISCOUNT = Decimal("0.15")
SALE_FROM = "2026-08-23T00:00:00"
SALE_TO = "2026-09-06T23:59:59"
CATEGORY = 522
BACKUP = os.path.join(os.path.dirname(__file__), "..", "data", "restore",
                      "bionova_prices_before_sale_2026-08-23.json")


def compute(regular: str) -> str:
    """15% off, rounded DOWN to the cent so we never round in our own favour."""
    r = Decimal(str(regular))
    return str((r * (Decimal("1") - DISCOUNT)).quantize(Decimal("0.01"),
                                                        rounding=ROUND_DOWN))


def put(path: str, payload: dict) -> dict:
    r = httpx.put(f"{BASE}/wp-json/wc/v3{path}", auth=AUTH, json=payload,
                  timeout=45)
    return {"status": r.status_code, "json": r.json()}


def main() -> int:
    clear = "--clear" in sys.argv
    if not all(AUTH):
        print("REFUSING: store credentials missing")
        return 1

    prods = store._get("/products", {"category": CATEGORY, "per_page": 100,
                                     "status": "publish"})
    backup, changed = [], 0

    for p in prods:
        name = p.get("name", "")[:44]
        if p.get("type") == "variable":
            vs = store._get(f"/products/{p['id']}/variations", {"per_page": 50})
            for v in (vs if isinstance(vs, list) else []):
                reg = (v.get("regular_price") or "").strip()
                if not reg:
                    continue
                backup.append({"product_id": p["id"], "variation_id": v["id"],
                               "name": name,
                               "regular_price": reg,
                               "sale_price": v.get("sale_price"),
                               "date_on_sale_from": v.get("date_on_sale_from"),
                               "date_on_sale_to": v.get("date_on_sale_to")})
                body = ({"sale_price": "", "date_on_sale_from": None,
                         "date_on_sale_to": None} if clear else
                        {"sale_price": compute(reg),
                         "date_on_sale_from": SALE_FROM,
                         "date_on_sale_to": SALE_TO})
                res = put(f"/products/{p['id']}/variations/{v['id']}", body)
                ok = res["status"] == 200
                changed += ok
                opt = [a.get("option") for a in (v.get("attributes") or [])]
                print(f"  {'OK ' if ok else '!! '}{name:<36} {str(opt)[:18]:<18}"
                      f" {reg:>8} -> {res['json'].get('sale_price') or '(cleared)'}")
        else:
            reg = (p.get("regular_price") or "").strip()
            if not reg:
                continue
            backup.append({"product_id": p["id"], "variation_id": None,
                           "name": name, "regular_price": reg,
                           "sale_price": p.get("sale_price"),
                           "date_on_sale_from": p.get("date_on_sale_from"),
                           "date_on_sale_to": p.get("date_on_sale_to")})
            body = ({"sale_price": "", "date_on_sale_from": None,
                     "date_on_sale_to": None} if clear else
                    {"sale_price": compute(reg),
                     "date_on_sale_from": SALE_FROM,
                     "date_on_sale_to": SALE_TO})
            res = put(f"/products/{p['id']}", body)
            ok = res["status"] == 200
            changed += ok
            print(f"  {'OK ' if ok else '!! '}{name:<36} {'(simple)':<18}"
                  f" {reg:>8} -> {res['json'].get('sale_price') or '(cleared)'}")

    if not clear:
        os.makedirs(os.path.dirname(BACKUP), exist_ok=True)
        with open(BACKUP, "w", encoding="utf-8") as fh:
            json.dump(backup, fh, indent=2, ensure_ascii=False)
        print(f"\nbacked up {len(backup)} price records -> data/restore/"
              f"bionova_prices_before_sale_2026-08-23.json")

    print(f"\n{'CLEARED' if clear else 'ON SALE'}: {changed} price points")
    if not clear:
        print(f"Runs {SALE_FROM[:10]} to {SALE_TO[:10]} then expires by itself.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
