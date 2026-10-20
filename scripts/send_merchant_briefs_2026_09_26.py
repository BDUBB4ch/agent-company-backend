"""Barry's #4 go (2026-09-26): barcode lookup to Priya, title redrafts to Derek.

Sends each brief through the normal office chat path, one after the other
(Bonsai runs one request at a time), and saves each reply to data/.
"""
import json
import httpx

API = "http://127.0.0.1:8420/api/chat"

PRIYA = """From Barry (relayed by Claude), work for Google Shopping visibility:

Our products send NO barcodes (GTIN/UPC/EAN) to Google Merchant Center, and that is a big reason they barely show in free listings. I need the REAL manufacturer barcode for each exact size of these products. First batch:

1. Bionova SiLution Mono-Silicic Acid: 250 ml, 1 L, 5 L
2. Dimlux CMH Lamp 315W: 3100K, 4100K
3. AB Lighting TL840 LED Grow Light: 120V, 240V, 277V
4. Bionova K 20 Potassium Mineral Additive: 1 L, 5 L, 20 L
5. Bionova Ca 15 Calcium Mineral Additive: 1 L, 5 L, 20 L
6. Bionova N27 Nitrogen Mineral Additive: 1 L, 5 L, 20 L
7. Bionova PK 13-14 Bloom Stimulator: 250 ml, 1 L, 5 L, 20 L
8. Bionova pH+ Liquid pH Adjuster: 1 L, 5 L, 20 L
9. Bionova Nutri Forte A + B Hydro: every size we list
10. Emerald Harvest Bloom (dry formulation): 2 lb, 25 lb

Rules, no exceptions:
- Use read_product first so you know the exact sizes we sell, then search_web for the barcode.
- A barcode counts ONLY if you found it written on a page that names that exact product AND that exact size (manufacturer site, distributor spec sheet, or a retailer listing that shows the UPC/EAN). Give the URL for every one.
- If you can't find it, write "not found". Never guess, never make up a number, never work out a check digit, never reuse one size's barcode for another size.
- If two sources disagree, list both with their URLs.

Deliver a table: product | size | barcode | type (UPC-12 / EAN-13) | source URL | how sure (found on manufacturer / found on retailer / not found). Nothing gets entered into the store until Barry confirms each one."""

DEREK = """From Barry (relayed by Claude), work for Google Shopping visibility:

Google Merchant Center flags or buries these 23 product titles: 8 are ALL CAPS (Google warns on them) and 15 are too short to match what people search for. Redraft each one.

ALL CAPS:
1. BIONOVA K 20 POTASSIUM MINERAL ADDITIVE
2. DIMLUX 315 WATT CERAMIC METAL HALIDE (CMH)
3. DIMLUX 630 WATT CERAMIC METAL HALIDE (CMH)
4. BIONOVA MICROMIX MINERAL ADDITIVE
5. BIONOVA MGO 10 MAGNESIUM MINERAL ADDITIVE
6. BIONOVA MICROLIFE MYCORRHIZA SOIL ENHANCER
7. THE LED GROW BOOK BY CHRISTOPHER SLOPER
8. DIMLUX EXPERT SERIES DE HPS FIXTURE W/ NANOTUBE - 1000W

TOO SHORT:
9. Mammoth P Active Microbials
10. GHF Mineral Line Calcium
11. GHF Mineral Line Long Flower
12. GHF Mineral Line Grow
13. Azapro Insecticide/Nematicide
14. Trellis Netting
15. GROWER'S ALLY Crop Defender 3
16. Grower's Ally Fungicide
17. GHF Bio Line BioEnhancer
18. GHF Bio Line BioBloom
19. GHF Bio Line BioGrow
20. GHF Mineral Line Booster PK+
21. GHF Mineral Line Short Flower
22. GHF Mineral Line Hybrids
23. Dimlux Maxi Controller

Rules:
- read_product on EVERY one before you write its title. Every word in the title must be true to that product's description, nothing assumed.
- Pattern: Brand + what it is + key spec (NPK, wattage, voltage, active ingredient, form) + who/what it's for in plain terms. Normal capitalization.
- The words people actually search go in the first 70 characters. Max 150 characters.
- CROP-NEUTRAL: these titles feed Google Shopping. No cannabis, no crop names that trip Google's policies; say "plants", "hydroponic", "soil", "indoor garden".
- No promo words (sale, best, free shipping, #1), no ALL CAPS words, no emoji.
- Leave sizes out of titles for products that come in several sizes (the feed adds the size per variant).
- Pesticide products (Azapro, Grower's Ally, Crop Defender): name what it is exactly as the label/description does, no health or safety claims.

Deliver a table: # | current title | new title | characters | one-line reason. Nothing changes on the store until Barry approves each one."""


def send(agent_id: str, message: str, out: str) -> None:
    r = httpx.post(API, json={"agent_id": agent_id, "message": message}, timeout=1800)
    r.raise_for_status()
    data = r.json()
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"{agent_id}: saved {out}")


if __name__ == "__main__":
    send("marketing", DEREK, "data/brief_derek_titles_2026-09-26.json")
    send("operations", PRIYA, "data/brief_priya_barcodes_2026-09-26.json")
