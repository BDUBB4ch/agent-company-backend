"""Full-catalogue margin audit: live store prices vs Global Garden wholesale cost.

WHY: two separate below-cost situations surfaced by accident on 2026-08-23 --
GHF Booster PK+ (three sizes, the 25kg losing $38.05 a sack) and Microlife
(nearly). Both had been live for months. Nobody was checking systematically.
This checks on purpose.

MATCHES BY SKU ONLY. The GG sheet and the store share `GG-` codes. Name
matching is what made the 2026-08-13 audit wrong twice, so it is not used.
Anything without a matching SKU is reported as unchecked, never guessed at.

READ-ONLY. Reports, changes nothing. Repricing stays a human decision.
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from dotenv import find_dotenv, load_dotenv  # noqa: E402

load_dotenv(find_dotenv())
import store  # noqa: E402

SHEET = os.path.join(os.path.dirname(__file__), "..", "data",
                     "bionova-evidence", "global-garden-wholesale-extracted.txt")

# GG-630124GHF Bio Line BioGrow - 500g (1.1lb) 10 $28.00 $55.95
ROW = re.compile(
    r"(GG-\d+)\s*(.+?)\s+(\d+)\s+\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})\s*$")

# Warn below this gross margin even when profitable.
THIN_PCT = 15.0


def load_costs() -> dict[str, dict]:
    out: dict[str, dict] = {}
    with open(SHEET, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = ROW.match(line.strip())
            if not m:
                continue
            sku, name, _qty, whl, srp = m.groups()
            out[sku.upper()] = {
                "name": name.strip()[:46],
                "cost": float(whl.replace(",", "")),
                "srp": float(srp.replace(",", "")),
            }
    return out


def live_prices() -> dict[str, dict]:
    out: dict[str, dict] = {}
    page = 1
    while page <= 5:
        prods = store._get("/products", {"per_page": 100, "page": page,
                                         "status": "publish"})
        if not isinstance(prods, list) or not prods:
            break
        for p in prods:
            if p.get("type") == "variable":
                for v in store._get(f"/products/{p['id']}/variations",
                                    {"per_page": 50}) or []:
                    sku = (v.get("sku") or "").strip().upper()
                    price = v.get("price") or v.get("regular_price")
                    if sku and price:
                        out[sku] = {"price": float(price),
                                    "name": p.get("name", "")[:40],
                                    "size": " ".join(
                                        str(a.get("option", "")) for a in
                                        (v.get("attributes") or []))[:16]}
            else:
                sku = (p.get("sku") or "").strip().upper()
                price = p.get("price") or p.get("regular_price")
                if sku and price:
                    out[sku] = {"price": float(price),
                                "name": p.get("name", "")[:40], "size": ""}
        page += 1
    return out


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace")
    costs, live = load_costs(), live_prices()
    print(f"cost rows parsed from GG sheet : {len(costs)}")
    print(f"live SKUs with a price         : {len(live)}")

    below, thin, ok, unchecked = [], [], 0, 0
    for sku, us in live.items():
        c = costs.get(sku)
        if not c:
            unchecked += 1
            continue
        margin = (us["price"] - c["cost"]) / us["price"] * 100.0
        row = (sku, us["name"], us["size"], c["cost"], us["price"], margin)
        if us["price"] <= c["cost"]:
            below.append(row)
        elif margin < THIN_PCT:
            thin.append(row)
        else:
            ok += 1

    below.sort(key=lambda r: r[5])
    thin.sort(key=lambda r: r[5])

    if below:
        print(f"\n{'='*78}\nSELLING AT OR BELOW COST ({len(below)}) -- "
              f"losing money on every sale\n{'='*78}")
        for sku, nm, sz, cost, price, m in below:
            print(f"  {nm:<40} {sz:<16} cost ${cost:>8,.2f}  price "
                  f"${price:>8,.2f}  LOSS ${cost - price:>7,.2f}")
    else:
        print("\nNothing at or below cost. Good.")

    if thin:
        print(f"\n{'='*78}\nTHIN MARGIN, under {THIN_PCT:.0f}% ({len(thin)})"
              f"\n{'='*78}")
        for sku, nm, sz, cost, price, m in thin:
            print(f"  {nm:<40} {sz:<16} cost ${cost:>8,.2f}  price "
                  f"${price:>8,.2f}  {m:>5.1f}%")

    print(f"\nhealthy: {ok}   |   unchecked (no GG cost row): {unchecked}")
    print("Unchecked means Bionova (bought from Winter, not GG), lighting, "
          "or anything GG does not list. Absence of a cost row is not "
          "evidence the price is fine.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
