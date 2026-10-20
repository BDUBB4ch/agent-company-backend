"""Consolidate the store / Microsoft Ads / Google state into the docs.

Barry, 2026-09-17: "you never update the .md on all the google stuff and the
microsoft ads things. do that now. save all this."

The facts were scattered across 08-13..08-29 session blocks, several of them
superseded (ads feed "not built", the Merchant Center flag "open"). This writes
ONE dated block at the top of the global CLAUDE.md and appends current-state
addenda to the two memory files. Idempotent: refuses to insert twice.
"""
import io
import os

MARKER = "## STORE / MICROSOFT ADS / GOOGLE -- CURRENT STATE"

BLOCK = '''## STORE / MICROSOFT ADS / GOOGLE -- CURRENT STATE (consolidated 2026-09-17; supersedes the scattered 08-13...08-29 entries below wherever they disagree)

Barry, 2026-09-17: "you never update the .md on all the google stuff and the
microsoft ads things. do that now." This block is the one place to read first.
Portable copy for outside tools: `Desktop/Claude-Extension-Brief-Store-Ads-Google.md`.

**THE STORE (bdubbgrowsllc.com)** -- WordPress on Hostinger, WooCommerce, Flatsome
(settings live in the Customizer), LiteSpeed Cache (purge after ANY front-end change
or you keep reading the old page), Rank Math, Poppins. ~119 products / ~421 with
variations. Lifetime 51 orders, ~$2,870; **zero orders of any status since
2026-08-14 while ads run -- so the leak is the landing page, not reach and not
checkout** (Sophie's `walk_checkout` proves checkout end to end). Payments LIVE
since 09-08: WooPayments + official WooCommerce PayPal only; every Stripe/Klarna
shaped plugin deactivated. Shipping $10 flat / free over $200; tax automated,
Colorado nexus ($0.00 before an address is entered is correct). **09-08 fixes, do
not re-fix:** Flatsome Add-To-Cart Button was `disable` (cards showed only a
wishlist icon) -> full button; Site Kit Consent Mode OFF + WP Consent API
deactivated (it had been denying ALL analytics collection); both AdTribes feeds
were "No Refresh" since March -> Daily; seven products rewritten at FEED level for
the Microsoft drug classifier. Tracking on the site: ONE Microsoft UET tag
(283008433), Microsoft Clarity (recording -- the right tool for "landed and left"),
Google Site Kit -> GA4 (excludes logged-in users, so test logged out), Google Ads
remarketing tag. Coupons: BIG15 = 15% off Bionova, BIG10 = 10% off everything else,
no minimum, first order, individual-use so they cannot combine (disclosed with a
footnote everywhere); BIG20 expired. The permanent ~22% GHF sale STAYS (his ruling,
heard twice -- do not re-raise). Open: the Legacy REST API plugin (confirm nothing
calls it first) and the YieldCraft rebrand (not started). Full store audit:
fact 2343 `sophie-store-ops-brain.md` (Sophie, on-demand) +
`Downloads/sophie-store-ops-brain.md`.

**MICROSOFT ADVERTISING (Bing ads)** -- one customer (cid 250620465), two accounts:
**F118AZ9A "B DUBB GROWS LLC" is THE account** (prepaid, $200 loaded 2026-08-28,
auto-recharge OFF on purpose); F118XMG9 "B DUBBB GROWS (tm)" is legacy with zero
campaigns -- never build there. **ONE CAMPAIGN RULE (his, verbatim ground rule):
only `Shopping_Search_032126_011052` runs, $10/day** -- never create another
without asking him. Measured 09-08 through the live API: 11,136 impressions / 82
clicks / $60.50 / 0 conversions per week (late-Aug snapshot: 766 impr / 21 clicks /
2.74% CTR / $0.25 CPC / 2 conv MTD). **Keeper UET tag = 283008433** ("B DUBB GROWS
LLC"), the only tag the site fires; its goals are add-to-cart, begin-checkout,
purchase. Inert undeletable leftovers, leave them alone: ShopifyImport (25136906),
B Dubb Grows IGS (283028897), GSF-WC24772 (283028937) -- conversion goals can only
be paused, never deleted, and a tag with goals attached cannot be deleted; the UET
Delete button froze Chrome three times in one session. **Product source for
Microsoft Shopping is the Google Import** (Simprosys -> Google Merchant Center ->
Microsoft Merchant Center). Simprosys's own Bing feed registration inside Microsoft
has an EMPTY feed file and no source URL -- do NOT add one without first confirming
whether Simprosys pushes by API, or every product duplicates. **Policy:** the "Drug
Content - General" classifier rejects grow tents and grow lights by CATEGORY, not
by wording accident -- fix it in Simprosys's per-product FEED editor (title,
description, product type), never in the live site copy, because the site has to
rank for what buyers actually search. Do not appeal until the corrected feed has
propagated (check the feed timestamp); premature appeals throttle the account's
appeal rate. Appeal still pending as of 09-08. Microsoft's own screens disagree
with each other (Diagnostics counted 15 rejections while the appeal queue said
none) -- when two screens conflict, go find the underlying feed record.
- ✅ **LIVE ADS DATA IS IN THE OFFICE (09-08) -- this supersedes the 08-28/08-30
  notes calling the feed "not built".** The Microsoft Ads reporting API is wired:
  five `MSADS_*` keys in `.env` (set by him), `backend/ads_api.py`, and the
  `ads_summary` tool on Sophie + Amara + Victor. The CSV-drop path (`ads_feed.py`,
  `drop/ads/`) survives as a fallback for token expiry or an API outage.
- Auth shape that actually works, learned the hard way: Entra app "Live ads feed" =
  **public client + native redirect + ONE interactive sign-in + a rolling refresh
  token + the developer token.** The Ads API has **no client-credentials / app-only
  flow** -- never create a client secret for it (that advice is for Microsoft
  Graph). Keep the app audience on **"any tenant + personal Microsoft accounts"**:
  his ads sit under a personal Microsoft account and single-tenant can lock out the
  very identity that owns them.

**GOOGLE (Merchant Center, Ads, Analytics)** -- **four Merchant Center accounts
exist, all named some variant of "B Dubb Grows"; `671622207` is THE one** (oldest,
holds the history, Verified + Claimed on bdubbgrowsllc.com, ~325 products). The
other three -- `5308352540`, `5308352951`, `5308368709` -- are empty shells.
⚠️ **Never click "Claim your online store" on a shell account:** it strips the claim
from 671622207 and flips all its products to Not approved, and the button sits
exactly where someone hunting for the verify screen would land. **Two Google
logins, and this is what once broke Simprosys:** `solidbdubb@gmail.com` owns and
admins 671622207, while `bdubbgrows@gmail.com` is what the Simprosys plugin is
authenticated as -- fixed 08-23 by adding that login as **Admin** (not Standard;
Standard cannot manage apps, which is what linking a feed tool requires).
**`Simprosys Feed (Merchant API)` is the single product pipeline.** Never leave two
live data sources on one account -- two pipelines (Google-for-WooCommerce plus
Simprosys) is exactly what produced the account-level Misrepresentation flag that
disapproved all 119 products in Aug 2026. Google for WooCommerce is set to
dont-sync-and-show but is still linked as an app and could start pushing again;
AdTribes' Product Feed PRO also generates two Google XML feeds (set to Daily on
09-08). ✅ **The Misrepresentation flag is RESOLVED** (Barry, 2026-08-29: "i dont
have a merchant center flag") -- do not raise it as outstanding. Some products
still sit in "Pending initial review". ⚠️ Merchant Center's UI panels contradict
each other constantly (Verified+Claimed on one page, a red unverified banner on
another) -- **ground truth is the product approval counts on Products & store ->
Products**, never a banner or a status chip. Merchant Center rejects CSV: convert
to tab-delimited `.txt` if a manual file is ever needed (it should not be --
Simprosys is the feed). Feed builders live in this repo: `scripts/export_google_feed.py`
(Google's column names; variable-product PARENTS excluded, variations tied by
`item_group_id`, sale price in `sale_price` never `price`) and
`scripts/export_products_csv.py`. There is **no grow-light category in Google's
taxonomy** -- use the honest broader parent, `Home & Garden > Lighting` (a 1000W
fixture was found in "Landscape Pathway Lighting"). Business address:
1919 Monterey Rd., Colorado Springs CO 80910. **Google Ads: no active spend** --
Microsoft is the one live campaign; the Google Ads remarketing tag is on the site;
copy for any Google surface stays crop-neutral. AdSense was removed from the store
2026-08-14. GA4 via Site Kit as above.
**PRIVACY, stated so it is never re-litigated:** none of this puts the OFFICE on a
Google server. These are Barry's own store and ads accounts, read by the office
through their APIs and by Claude through his own browser sessions; the office's own
search is DuckDuckGo/SearXNG only and every service is bound to 127.0.0.1.

'''

MS_ADDENDUM = '''

**UPDATE 2026-09-17 (current state -- supersedes the "feed NOT built" line above).**
The live Microsoft Ads reporting API has been wired since 09-08: `backend/ads_api.py`,
five `MSADS_*` keys in `.env`, tool `ads_summary` on Sophie / Amara / Victor.
Measured then: 11,136 impressions / 82 clicks / $60.50 / 0 conversions per week.
The CSV drop is a fallback only. Still exactly one campaign
(`Shopping_Search_032126_011052`, $10/day, account F118AZ9A) and one UET tag firing
on the site (283008433). Simprosys's Bing feed registration inside Microsoft
Merchant Center is empty with no source URL -- do not add one (duplication risk);
products reach Microsoft through the Google Import. The drug-content policy appeal
is pending; the seven feed-level product rewrites landed 09-08. The consolidated
state now lives at the TOP of the global CLAUDE.md under
"STORE / MICROSOFT ADS / GOOGLE -- CURRENT STATE".
'''

GOOG_ADDENDUM = '''

**UPDATE 2026-09-17 (current state).** The account-level Misrepresentation flag is
RESOLVED (Barry, 2026-08-29) -- never raise it as open. `Simprosys Feed (Merchant
API)` remains the single pipeline on 671622207 (~325 products); Google for
WooCommerce is dont-sync but still linked as an app; AdTribes' two Google XML feeds
were set to Daily on 09-08; seven products were rewritten at feed level for the
Microsoft drug classifier; some products still sit in "Pending initial review".
There is no grow-light category in Google's taxonomy -- use Home & Garden >
Lighting. Google Ads has no active spend; Microsoft is the only live campaign. The
consolidated state now lives at the TOP of the global CLAUDE.md under
"STORE / MICROSOFT ADS / GOOGLE -- CURRENT STATE".
'''


def main() -> None:
    home = os.path.expanduser("~")
    claude_md = os.path.join(home, ".claude", "CLAUDE.md")
    mem = os.path.join(home, ".claude", "projects",
                       "C--Users-Owner-Desktop-AgentCompanyBackend", "memory")

    s = io.open(claude_md, encoding="utf-8").read()
    if MARKER in s:
        print("global CLAUDE.md: block already present, skipped")
    else:
        anchor = "## Components and ports"
        assert s.count(anchor) == 1, "anchor moved -- check the file by hand"
        s = s.replace(anchor, BLOCK + anchor, 1)
        tmp = claude_md + ".tmp"
        io.open(tmp, "w", encoding="utf-8", newline="").write(s)
        os.replace(tmp, claude_md)
        print(f"global CLAUDE.md: inserted {len(BLOCK)} chars above '{anchor}'")

    for name, add in (("microsoft-ads-setup.md", MS_ADDENDUM),
                      ("google-merchant-center-setup.md", GOOG_ADDENDUM)):
        path = os.path.join(mem, name)
        body = io.open(path, encoding="utf-8").read()
        if "UPDATE 2026-09-17" in body:
            print(f"{name}: addendum already present, skipped")
            continue
        io.open(path, "a", encoding="utf-8").write(add)
        print(f"{name}: addendum appended")


if __name__ == "__main__":
    main()
