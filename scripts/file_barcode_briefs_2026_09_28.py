"""Barry's #5 (2026-09-28): redo the barcode hunt as ONE product per brief.

Brief #50 (all ten products in one job) ran past the time limit twice and was
filed as "done, 0 chars". Its row is corrected to failed, and ten small briefs
go on the board -- the board works one at a time.
"""
import sys
sys.path.insert(0, "backend")
import memory
import teamwork

PRODUCTS = [
    ("Bionova SiLution Mono-Silicic Acid", "250 ml, 1 L, 5 L (there is NO 20 L)"),
    ("Dimlux CMH Lamp 315W", "3100K, 4100K"),
    ("AB Lighting TL840 LED Grow Light", "120V, 240V, 277V"),
    ("Bionova K 20 Potassium Mineral Additive", "1 L, 5 L, 20 L"),
    ("Bionova Ca 15 Calcium Mineral Additive", "1 L, 5 L, 20 L"),
    ("Bionova N27 Nitrogen Mineral Additive", "1 L, 5 L, 20 L"),
    ("Bionova PK 13-14 Bloom Stimulator", "250 ml, 1 L, 5 L, 20 L"),
    ("Bionova pH+ Liquid pH Adjuster", "1 L, 5 L, 20 L"),
    ("Bionova Nutri Forte A + B Hydro", "all 9: A, B and A&B, each in 1 L, 5 L, 20 L"),
    ("Emerald Harvest Bloom - Dry Formulation", "2 lb canister, 6 lb bucket, 25 lb bag"),
]

TEMPLATE = """From Barry, in his words (relayed by Claude): find the REAL manufacturer barcode (UPC / EAN / GTIN) for ONE product, every size we sell:

PRODUCT: {name}
SIZES: {sizes}

Rules, no exceptions:
- read_product first to confirm the exact sizes on our store, then search_web. Keep it tight -- a handful of searches, not dozens.
- A barcode counts ONLY if a page names that exact product AND that exact size: manufacturer site, distributor spec sheet, or a retailer listing that shows the UPC/EAN. Give the URL for every one.
- Not found = write "not found". Never guess, never make up a number, never work out a check digit, never reuse one size's barcode for another size. Two sources disagree = list both with URLs.

Deliver a short table: size | barcode | type (UPC-12 / EAN-13) | source URL | found on (manufacturer / retailer / not found). Nothing goes into the store until Barry confirms each one."""

with memory.get_db() as conn:
    conn.execute("UPDATE briefs SET status='failed', reply=? WHERE id=50 AND status='done'",
                 ("[failed: timed out twice (900s), 0 chars delivered -- re-filed 2026-09-28 as one brief per product]",))

ids = [teamwork.file_brief("CIO", "Operations", TEMPLATE.format(name=n, sizes=s)) for n, s in PRODUCTS]
print("filed briefs:", ids)
