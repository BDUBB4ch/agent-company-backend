"""Barry's yes (2026-09-26): Derek redoes #8/#14/#23, Priya runs the barcode hunt now."""
import json
import httpx

API = "http://127.0.0.1:8420/api/chat"

DEREK = """From Barry (relayed by Claude): three of your 23 titles need redoing. The other 19 go to Barry for approval as you wrote them.

- #23: your title is for the WRONG product. The store has "Dimlux Maxi Controller" (the controller itself) AND separate "Dimlux Co2 Sensor for Maxi Controller" listings; the product lookup handed you the sensor by mistake (that lookup bug is fixed now). Call read_product with "Dimlux Maxi Controller" again, confirm the PRODUCT line says exactly that, and write the controller's title from its own description.
- #8: drop "240/277V". That Expert Series fixture lists no voltage; don't add a spec the page doesn't state.
- #14: drop "B Dubb Grows". Trellis Netting has no brand set, and Google wants the manufacturer or nothing, never the store's name.

Same rules as before. Give just the three corrected rows: # | current title | new title | characters | reason."""

PRIYA = """From Barry (relayed by Claude): go now, don't wait for Monday.

Sizes: every size the store actually sells, EXCEPT there is no SiLution 20 L. SiLution is 250 ml, 1 L and 5 L only (read_product "Bionova SiLution Mono-Silicic Acid" shows three). Nutri Forte = all 9 (A, B, A&B x 1/5/20 L). Emerald Harvest Bloom = the DRY FORMULATION product: 2 lb canister, 6 lb bucket, 25 lb bag.

Run the barcode search now with search_web, product by product, same rules: a barcode counts ONLY if a page names that exact product AND exact size; URL for every one; "not found" otherwise; no guessing, no check-digit math, no reusing a barcode across sizes.

Deliver the table: product | size | barcode | type (UPC-12 / EAN-13) | source URL | how sure."""


def send(agent_id: str, message: str, out: str) -> None:
    r = httpx.post(API, json={"agent_id": agent_id, "message": message}, timeout=2400)
    r.raise_for_status()
    with open(out, "w", encoding="utf-8") as f:
        json.dump(r.json(), f, indent=2, ensure_ascii=False)
    print(f"{agent_id}: saved {out}")


if __name__ == "__main__":
    send("marketing", DEREK, "data/brief_derek_titles_fix_2026-09-26.json")
    send("operations", PRIYA, "data/brief_priya_barcodes_run_2026-09-26.json")
