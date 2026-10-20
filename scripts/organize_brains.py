"""Organize the always-on brain: give every shared fact a clear TITLE line,
put them in a deliberate reading order, and drop true duplication.

Nothing is deleted. Old rows are marked 'superseded' (memory.py's own
history-preserving mechanism) and rewritten versions are re-inserted with
controlled created_at so they render in a sensible order.

Run:  ../venv/Scripts/python.exe scripts/organize_brains.py --apply
Without --apply it prints a dry-run diff and changes nothing.
"""
import sys
import os
import argparse
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import memory  # noqa: E402

SKILL = "product-catalog-full"

# Reading order within each category. Each entry:
#   (category, source_name, title, body)
# Order in this list == order the agent reads them.
PLAN = [
    (
        "owner", "",
        "OWNER -- WHO HE IS",
        "Barry Jermaine White (goes by B DUBB / Barry White in creative credits). "
        "Every agent in this office works directly for him personally, across all "
        "three ventures. Address him by name when it feels natural, not performatively.",
    ),
    (
        "owner", "",
        "OWNER -- WHAT HE IS BUILDING TOWARD",
        "Long-term goal: build real, substantial wealth from these businesses -- enough "
        "to buy land and build a house in Florida. Not a task to act on; it is why "
        "growth, margin and smart reinvestment recommendations matter to him beyond "
        "day-to-day operations.",
    ),
    (
        "business:bdubbgrows", "",
        "B DUBB GROWS -- WHAT IT IS",
        "B Dubb Grows LLC (bdubbgrowsllc.com, info@bdubbgrowsllc.com) is Barry's primary "
        "business and main money-maker. Legal and operating name is B Dubb Grows LLC -- "
        "NOT 'YieldCraft', a rename that was considered and never happened.\n"
        "Premium indoor/hydroponic gardening SUPPLY retailer, running on WooCommerce: "
        "nutrients and minerals, grow lights, grow tents, RO/water filtration, plant "
        "additives, accessories.\n"
        "Offers: free shipping over $200; 15% newsletter signup discount.\n"
        "Social: IG @b.dubb_growsllc | FB @BDUBB4ch | TikTok @bdubbgrows | "
        "X @BDUBB64760448 | YouTube @BDUBBGROWS",
    ),
    (
        "business:bdubbgrows", "",
        "B DUBB GROWS -- AUDIENCE AND CROP POLICY (Barry's own rule, 2026-08-03)",
        "Supersedes any older 'vegetables, herbs and houseplants only' note.\n"
        "WHAT IT SELLS: what plants eat and what growers use. No plants, no cannabis, no "
        "controlled substance -- so it is an ANCILLARY business, not plant-touching.\n"
        "WHO IT SPEAKS TO: ALL growers -- cannabis, vegetables, fruit, herbs, houseplants. "
        "Barry is himself a cannabis grower and breeder and many customers are too, so "
        "cannabis-grower content is a completely normal request. Make it well, no hedging, "
        "and NEVER swap his ask for a 'safer' crop. The site hero already shows cannabis "
        "alongside other plants. Default to all-growers framing only when he has not specified.\n"
        "TWO HARD EXCLUSIONS, and only two -- keep cannabis OUT of: (1) Google Ads copy, "
        "(2) WooCommerce product descriptions. Product copy feeds Google Shopping, where "
        "cannabis language gets listings disapproved and can cost the ad account. "
        "Everywhere else -- blog, organic social, email -- cannabis is fine.",
    ),
    (
        "business:bdubbgrows", "bdubb-product-catalog",
        "B DUBB GROWS -- PRODUCT CATALOG (categories, brands, and where the real data lives)",
        "CATEGORY PAGES -- link these when pointing at a range:\n"
        "- Nutrients & Fertilizers: https://bdubbgrowsllc.com/product-category/bionova-premium-fertilizer-additives/\n"
        "- Bionova Line: https://bdubbgrowsllc.com/product-category/bionova-line/\n"
        "- Plant Additives: https://bdubbgrowsllc.com/product-category/additives/\n"
        "- Grow Lights: https://bdubbgrowsllc.com/product-category/grow-lights/\n"
        "- Grow Tents: https://bdubbgrowsllc.com/product-category/grow-tents/\n"
        "- Water Systems & RO: https://bdubbgrowsllc.com/product-category/water-filtration-reverse-osmosis-systems/\n"
        "- Plant Care & Accessories: https://bdubbgrowsllc.com/product-category/accessories/\n"
        "BRANDS CARRIED: Bionova (flagship -- soil, hydro and coco lines), Emerald Harvest "
        "(2-part and 3-part base series), General Hydroponics (Bio Line, Mineral Line), "
        "HighDroGro (tents), GrowMax Water (RO), Grower's Ally (plant care).\n"
        "BASE NUTRIENT IS CHOSEN BY MEDIUM: Soil Supermix (soil), Nutri Forte A+B (hydro), "
        "Coco Forte A+B (coco). Single-mineral additives for targeted fixes: N27, P20, K20, "
        "Ca15, MgO10, MicroMix. Stage/biology boosters: PK 13-14, The Missing Link, MicroLife. "
        "Water management: pH+ and pH-.\n"
        "*** FOR ANY PRODUCT WORK (posts, emails, recommendations, visuals) READ THE "
        + SKILL +
        " SKILL FIRST. *** It holds all 119 products with prices, descriptions, exact page "
        "URLs, and the REAL PRODUCT PHOTO URL for each. When a post features a product use "
        "its real photo URL from that skill -- a generated image is never the actual product; "
        "generated scenes are mood and b-roll only. Never invent a product URL: if unsure a "
        "product exists or is in stock, link the CATEGORY page instead.",
    ),
    (
        "business:bdubbgrows", "",
        "B DUBB GROWS -- BRAND VOICE (canonical, Barry's own words)",
        "VOICE: a knowledgeable grower talking to other growers. Direct, results-focused, "
        "educational -- no fluff, no corporate distance. Platform-smart, never pushy: "
        "education leads, the CTA follows quietly.\n"
        "TWO MODES, chosen from the ask and never announced:\n"
        "  (a) TECHNICAL, for serious cultivators -- real numbers, EC/ppm, VPD, runoff pH, "
        "exact ranges, assumes the fundamentals.\n"
        "  (b) APPROACHABLE, for home growers -- plain terms like feed strength and humidity, "
        "rules of thumb, explain a term on first use. Approachable means SIMPLER, never "
        "talking down.\n"
        "UVP: 'Clean nutrients, honest education, and real-world results -- from a "
        "Colorado-based grower who actually uses and tests the products they sell.'\n"
        "CORE FRAME: minerals are minerals and all plants eat them -- the chemistry does not "
        "change with the crop. Crop differences worth naming are the real ones (photoperiod, "
        "feed strength, EC tolerance, harvest timing), not different product lines.",
    ),
    (
        "business:bdubbgrows", "",
        "B DUBB GROWS -- EMAIL PLATFORMS (settled 2026-08-03; trust THIS one)",
        "OMNISEND is the bulk marketing platform for the B Dubb Grows list. Barry moved to "
        "Omnisend and cancelled the MC4WP (Mailchimp for WordPress) plugin. Mailchimp is NO "
        "LONGER the platform -- ignore any older note saying it is.\n"
        "TITAN (info@bdubbgrowsllc.com, his own domain) stays for one-to-one mail: customer "
        "replies, vendors, and ALL PID partner outreach. Never route PID through a marketing "
        "platform.\n"
        "CROP POLICY FOR EMAIL, relaxed: Omnisend's terms do not name cannabis and it is "
        "generally cannabis-tolerant for email, so the old Mailchimp restriction is GONE and "
        "cannabis-forward email is acceptable again.\n"
        "SMS IS DIFFERENT EVERYWHERE: cannabis limits there are carrier-driven (CTIA/SHAFT), "
        "attach to the business CATEGORY not the message, and are enforced via A2P 10DLC "
        "registration. Never plan cannabis-forward SMS.",
    ),
    (
        "business:gotchoback", "",
        "GOTCHO BACK -- WHAT IT IS",
        "Gotcho Back (gotchoback.com) is Barry's second business -- a fashion-forward backpack "
        "brand, tagline 'Where Backpacks Are Fashion'. School backpacks, fashion backpacks, "
        "hemp backpacks, leather options, convertible backpack-to-handbag designs, sling bags. "
        "Roughly $22-$68.\n"
        "VOICE: casual, youth-oriented, style-first -- backpacks as a style statement, not a "
        "functional item. Audience: students, young professionals, fashion-conscious buyers.\n"
        "Social: IG @gotcho.back\n"
        "SEPARATE brand and product line from B Dubb Grows. Never mix gardening-supply "
        "language into Gotcho Back content, or vice versa.",
    ),
    (
        "business:pid", "",
        "PID -- WHAT IT IS, AND THE HARD SEPARATION RULE",
        "PID (Personal Intelligent Device, piddevice.com, info@piddevice.com) is Barry's THIRD "
        "venture, separate from B Dubb Grows LLC and Gotcho Back. A sovereign, privacy-first, "
        "Linux-based handheld: no Android layer, no Google dependencies, no trackers, "
        "offline-first Vault, personal AI the user owns, mesh built in, plus the PID Home Dock "
        "as a private internet gateway. Barry J. White is Founder (permanent, non-negotiable).\n"
        "STATUS: PRE-HARDWARE. It is a Founder Bible and an outreach plan seeking an ODM "
        "manufacturing partner. It does NOT exist as a shipping product, has NO signed "
        "partners, and its pricing and unit economics are explicitly UNVALIDATED. Never imply "
        "otherwise.\n"
        "HARD SEPARATION (Barry's repeated instruction): 'PID is its own business, never to be "
        "mixing with B Dubb Grows or Gotcho Back'; 'nothing feeds PID'; 'don't ever mix "
        "businesses in conversation.' No shared customers, no shared branding, no "
        "cross-promotion, no B Dubb voice in PID material.\n"
        "BEFORE PRODUCING ANY PID WORK -- a draft, an email, a deck line, a recommendation -- "
        "read the pid-guardrails skill first.",
    ),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    cats = sorted({c for c, _s, _t, _b in PLAN})
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT id, category, source_name, length(content) AS c FROM facts "
            "WHERE status='active' AND category IN (%s)" % ",".join("?" * len(cats)),
            cats,
        ).fetchall()
    old = [dict(r) for r in rows]
    old_total = sum(r["c"] for r in old)
    new_total = sum(len(t) + 2 + len(b) for _c, _s, t, b in PLAN)

    print("categories organized:", ", ".join(cats))
    print("BEFORE: %d always-on facts, %d chars" % (len(old), old_total))
    print("AFTER : %d always-on facts, %d chars" % (len(PLAN), new_total))
    print("delta : %+d chars" % (new_total - old_total))
    for r in old:
        print("   supersede id=%-4s %-22s %5d chars" % (r["id"], r["category"], r["c"]))
    if not args.apply:
        print("\nDRY RUN -- nothing changed. Re-run with --apply")
        return

    base = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    with memory.get_db() as conn:
        conn.execute(
            "UPDATE facts SET status='superseded' WHERE status='active' AND category IN (%s)"
            % ",".join("?" * len(cats)),
            cats,
        )
        for i, (cat, src, title, body) in enumerate(PLAN):
            conn.execute(
                "INSERT INTO facts (category, content, source_name, created_at, status) "
                "VALUES (?,?,?,?, 'active')",
                (cat, title + "\n" + body, src,
                 (base + datetime.timedelta(minutes=i)).isoformat()),
            )
    print("\nAPPLIED. Old rows kept as status='superseded' (recoverable).")


if __name__ == "__main__":
    main()
