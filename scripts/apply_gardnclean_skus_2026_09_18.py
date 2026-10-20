"""Apply Gard'nClean variant SKUs from Global Garden's own catalog.

Barry, 2026-09-17: "Each one needs its parent SKU cleared first, same as the
two I did -- the parent currently holds one of the variant numbers, and that
collision is what jams the save."  Then: "get the sku from global garden."

Codes verified against data/bionova-evidence/global-garden-wholesale-extracted.txt
lines 76-92 (Fast Release GG-670100..103, Extended Release GG-670104..107,
Liquid Mix GG-670108..110, Test Strips GG-660100 Wide / GG-660101 Low).

Clears the parent SKU first, then writes each variation, then RE-READS every
row so nothing is reported from the request instead of the result.
"""
import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv(r"C:\Users\Owner\Desktop\AgentCompanyBackend\.env")

URL = os.environ["STORE_URL"].rstrip("/")
AUTH = (os.environ["STORE_CONSUMER_KEY"], os.environ["STORE_CONSUMER_SECRET"])
API = f"{URL}/wp-json/wc/v3"

# product_id -> (label, {variation_id: sku})
PLAN = {
    1595: ("Liquid Mix Disinfectant", {
        1949: "GG-670108",   # 2 gal.
        1948: "GG-670109",   # 12.5 gal.
        1950: "GG-670110",   # 30 gal.
    }),
    1593: ("Fast Release Dry Gas Deep Deodorizer", {
        1951: "GG-670100",   # 1k
        1952: "GG-670101",   # 2.5k  (was GG-67101 -- typo, one zero short)
        1953: "GG-670102",   # 4k
        1954: "GG-670103",   # 10k
    }),
    1594: ("Extended Release Deodorizer", {
        1955: "GG-670104",   # 1k
        1956: "GG-670105",   # 2.5
        1957: "GG-670106",   # 4k
        1958: "GG-670107",   # 10k
    }),
    1596: ("Chlorine Dioxide Test Strips", {
        1946: "GG-660100",   # Wide Range
        1947: "GG-660101",   # Low Range
    }),
}


def put(path, payload):
    r = requests.put(f"{API}/{path}", auth=AUTH, json=payload, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f"{path} -> {r.status_code} {r.text[:300]}")
    return r.json()


def get(path):
    r = requests.get(f"{API}/{path}", auth=AUTH, timeout=60)
    r.raise_for_status()
    return r.json()


def main():
    failures = []
    for pid, (label, variants) in PLAN.items():
        print(f"\n=== {label} (id {pid})")
        parent = get(f"products/{pid}")
        if parent.get("sku"):
            print(f"  parent SKU '{parent['sku']}' -> clearing (collision)")
            put(f"products/{pid}", {"sku": ""})
            time.sleep(0.4)
            again = get(f"products/{pid}")
            if again.get("sku"):
                failures.append(f"{label}: parent SKU still '{again['sku']}'")
                print(f"  !! parent clear FAILED, still '{again['sku']}' -- skipping variants")
                continue
            print("  parent SKU cleared (verified)")
        else:
            print("  parent SKU already empty")

        for vid, sku in variants.items():
            before = get(f"products/{pid}/variations/{vid}")
            old = before.get("sku") or "(empty)"
            if old == sku:
                print(f"  var {vid}  {before['name'].split('-')[-1].strip()[:20]:<22} already {sku}")
                continue
            put(f"products/{pid}/variations/{vid}", {"sku": sku})
            time.sleep(0.4)
            after = get(f"products/{pid}/variations/{vid}")
            got = after.get("sku") or "(empty)"
            ok = got == sku
            if not ok:
                failures.append(f"{label} var {vid}: wanted {sku}, store says {got}")
            print(f"  var {vid}  {old:<14} -> {got:<14} {'OK' if ok else '!! MISMATCH'}")

    print("\n--- re-read of every row ---")
    for pid, (label, variants) in PLAN.items():
        parent = get(f"products/{pid}")
        print(f"{label:<40} parentSKU={parent.get('sku') or '(empty)'!r}")
        for v in get(f"products/{pid}/variations?per_page=50"):
            print(f"    {v['id']}  {v.get('sku') or '(empty)':<14} ${v.get('price')}")

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  " + f)
        sys.exit(1)
    print("\ndone: all SKUs written and verified by re-read")


if __name__ == "__main__":
    main()
