"""Competitor price watch -- READ-ONLY, outbound.

Built 2026-08-23 after finding B Dubb priced ~50% above Hydrobuilder on the
entire Green House Feeding line, and three Booster PK+ sizes selling BELOW
COST. Both had gone unnoticed for months because nobody was checking.

HOW IT MATCHES: by SKU, not by name. Hydrobuilder lists the same Global Garden
`GG-` SKUs Barry carries, exposed in Shopify's public
/collections/<x>/products.json. An exact SKU match cannot drift the way a
fuzzy name match does -- which matters, because the last pricing audit was
wrong twice from matching on names.

WHAT IT CANNOT DO, stated plainly so nobody over-trusts it:
  - Only covers lines where the competitor uses the same SKU. Emerald Harvest
    is listed there under their own SKUs, so EH returns no matches and says so
    rather than guessing.
  - One competitor. Barry's own pricing rule wants three live references
    before setting a price; this is one of them, not all three.
  - It reports. It never changes a price. Repricing stays a human decision.

Offline Mode must strip this like web search and the store tools -- it makes
outbound calls to a public site.
"""
from __future__ import annotations

import json
import os

import httpx

import store

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# competitor -> collections worth scanning. Add lines here as Barry adds them.
COMPETITORS = {
    "hydrobuilder.com": [
        "green-house-feeding",
        "emerald-harvest",
        "bionova",
    ],
}

CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "data",
                          "competitor_prices_last.json")


def _fetch_collection(host: str, handle: str) -> list[dict]:
    """Shopify's public products.json. Returns [] on any failure -- a
    competitor changing their site must never break an agent's turn."""
    url = f"https://{host}/collections/{handle}/products.json?limit=250"
    try:
        r = httpx.get(url, headers={"User-Agent": UA}, timeout=30,
                      follow_redirects=True)
        if r.status_code != 200:
            return []
        return r.json().get("products", [])
    except Exception:  # noqa: BLE001
        return []


def _competitor_index() -> dict[str, dict]:
    """sku -> {price, available, title, size, host}"""
    idx: dict[str, dict] = {}
    for host, handles in COMPETITORS.items():
        for handle in handles:
            for p in _fetch_collection(host, handle):
                for v in p.get("variants", []):
                    sku = (v.get("sku") or "").strip()
                    if not sku:
                        continue
                    try:
                        price = float(v.get("price"))
                    except (TypeError, ValueError):
                        continue
                    idx[sku.upper()] = {
                        "price": price,
                        "available": bool(v.get("available")),
                        "title": p.get("title", ""),
                        "size": v.get("title", ""),
                        "host": host,
                    }
    return idx


def _our_prices() -> dict[str, dict]:
    """sku -> {price, name, size} from the live store, variations included."""
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
                    sku = (v.get("sku") or "").strip()
                    price = v.get("price") or v.get("regular_price")
                    if sku and price:
                        out[sku.upper()] = {
                            "price": float(price),
                            "name": p.get("name", ""),
                            "size": " ".join(str(a.get("option", "")) for a
                                             in (v.get("attributes") or [])),
                        }
            else:
                sku = (p.get("sku") or "").strip()
                price = p.get("price") or p.get("regular_price")
                if sku and price:
                    out[sku.upper()] = {"price": float(price),
                                        "name": p.get("name", ""), "size": ""}
        page += 1
    return out


def check_prices(threshold_pct: float = 5.0) -> str:
    """Compare live store prices to competitor listings, matched by SKU.

    threshold_pct: only report gaps wider than this, either direction.
    """
    comp = _competitor_index()
    if not comp:
        return ("Could not reach any competitor site just now. Nothing was "
                "changed. Try again later, or tell Barry it is unreachable.")

    ours = _our_prices()
    if not ours:
        return ("Could not read our own store prices -- check the store "
                "credentials. Nothing was compared.")

    matched, higher, lower, their_oos = [], [], [], []
    for sku, us in ours.items():
        them = comp.get(sku)
        if not them:
            continue
        matched.append(sku)
        gap = (us["price"] - them["price"]) / them["price"] * 100.0
        row = {"sku": sku, "name": us["name"][:40], "size": us["size"][:14],
               "ours": us["price"], "theirs": them["price"],
               "gap_pct": gap, "their_stock": them["available"],
               "host": them["host"]}
        if gap > threshold_pct:
            higher.append(row)
        elif gap < -threshold_pct:
            lower.append(row)
        if not them["available"]:
            their_oos.append(row)

    higher.sort(key=lambda r: -r["gap_pct"])
    lower.sort(key=lambda r: r["gap_pct"])

    lines = [f"COMPETITOR PRICE CHECK -- {len(matched)} products matched by SKU "
             f"against {', '.join(COMPETITORS)}."]

    if higher:
        lines.append(f"\nWE ARE MORE EXPENSIVE ({len(higher)}) -- losing the sale:")
        for r in higher[:20]:
            lines.append(f"  {r['name']} {r['size']}: us ${r['ours']:.2f} vs "
                         f"${r['theirs']:.2f} (+{r['gap_pct']:.0f}%)")
    else:
        lines.append("\nNothing priced materially above them. Good.")

    if lower:
        lines.append(f"\nWE ARE CHEAPER ({len(lower)}):")
        for r in lower[:15]:
            lines.append(f"  {r['name']} {r['size']}: us ${r['ours']:.2f} vs "
                         f"${r['theirs']:.2f} ({r['gap_pct']:.0f}%)")

    if their_oos:
        lines.append(f"\nTHEY ARE OUT OF STOCK ({len(their_oos)}) -- we can win "
                     f"these right now if we have them:")
        for r in their_oos[:15]:
            lines.append(f"  {r['name']} {r['size']} (their price "
                         f"${r['theirs']:.2f})")

    unmatched = len(ours) - len(matched)
    lines.append(f"\n{unmatched} of our SKUs had no match there -- either they "
                 f"do not carry it, or they list it under a different SKU "
                 f"(Emerald Harvest is one of those). Absence is not evidence "
                 f"they lack it.")
    lines.append("This is ONE competitor. Barry's rule is three live "
                 "references before changing a price. Report the numbers; "
                 "do not reprice anything yourself.")

    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as fh:
            json.dump({"higher": higher, "lower": lower,
                       "their_oos": their_oos}, fh, indent=2)
    except Exception:  # noqa: BLE001 -- caching must never break the report
        pass

    return "\n".join(lines)


if __name__ == "__main__":
    print(check_prices())
