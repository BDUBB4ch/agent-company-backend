"""Barry, 2026-09-26: "tell Sophie and the team what we found".

One always-on fact in business:bdubbgrows (reaches the business seats; Elliot,
Taliyah and hires are walled off by memory's exclusions). Supersedes nothing.
"""
import sys
sys.path.insert(0, "backend")
import memory

CONTENT = """STORE FINDINGS -- 2026-09-25/26 (Barry + Claude, verified on the live systems)

TRAFFIC: the "713 visitors" in the Woo app / Jetpack on 09-25 was a bot -- 711 from China, 700 on the homepage only, 1 view each, bursts on odd hours. Barry blocked China at the Hostinger CDN. Real traffic is about 7-30 visitors a day. Jetpack visitor counts are NOT evidence of shoppers; no office tool counts visitors.

WHERE BUYERS COME FROM (buyer_sources, 90 days): DuckDuckGo 2 orders $1,487.20 (both landed on the Dimlux CMH 315W page); Google free Shopping listings 2 orders $483.46. No paid ads (Microsoft Ads paused).

MERCHANT CENTER 671622207: 360 of 361 approved, free listings on, but only 38 impressions in 28 days. Simprosys is the only feed (323 items, re-synced). Google for WooCommerce plugin DEACTIVATED 09-26 (its old gla_ items expire on their own). Nothing on the store sends a barcode (GTIN) -- Priya's barcode brief is the fix; a barcode is only used if found on a page naming the exact product and size.

FIXED: 77 expired sale prices (Bionova sale Aug 23-Sep 6) cleared -- regular prices unchanged. 23 product titles rewritten (Barry approved each; crop-neutral). walk_checkout now tests the cheapest size (the $721.64 cart was the 5 L SiLution, not customer friction).

EMAIL CAPTURE: the Omnisend welcome popup (BIG15 Bionova / BIG10 everything else) was live since Aug 12 but had NO display trigger -- 20 views, 0 signups. Now opens at 10 seconds, 40% scroll, or exit intent. The Welcome email delivers both codes.

OPEN: Oct 9 -- a "Found by Google" source appears in Merchant Center; Barry turns it off ("Stop managing products") so Simprosys stays the only source."""

memory.add_fact("business:bdubbgrows", CONTENT, source_name="store-findings-2026-09-26",
                title="STORE FINDINGS -- 2026-09-25/26")
print("added", len(CONTENT), "chars")
