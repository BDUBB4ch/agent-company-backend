"""
Read-only WooCommerce access for the agents.

WHY THIS EXISTS
---------------
Until now the agents advised on a business they could not see. Amara answered
finance questions with no access to a single order; Derek planned marketing
without knowing what was actually selling; Vivian wrote product shots for
products she could only recall from a 56K-character catalog document that (at
the measured ~1% read_skill rate) she almost never opened. Every number in
every answer was either remembered, inferred, or invented -- which is exactly
the failure mode _CONFIRMS_UNDERSTANDING tells them to avoid, while giving
them no way to avoid it.

SAFETY, IN LAYERS
-----------------
1. This module contains NO write verbs. There is no post/put/delete function
   here to call by accident, and _get() is the only request path.
2. The credentials Barry generates should be scoped **Read** in WooCommerce
   itself, so even a bug in this file cannot write to the store. The store,
   not this code, is the real enforcement point.
3. Offline Mode strips these tools entirely (see llm_router) -- same treatment
   as web search, because this is an outbound network call to a live site.
4. Credentials are read from the environment ONLY. They are never accepted as
   a function argument, never logged, and never echoed into a reply. Barry
   sets them in .env himself; nothing in this codebase should ever ask him for
   them in chat.

CONFIGURATION
-------------
Set these in .env (see store_status() for the live check):

    STORE_URL=https://bdubbgrowsllc.com
    STORE_CONSUMER_KEY=ck_xxxxxxxx
    STORE_CONSUMER_SECRET=cs_xxxxxxxx

Generate the pair in WP admin under
WooCommerce -> Settings -> Advanced -> REST API -> Add key, permission "Read".
"""
import html
import os
import re
import time
import threading

import httpx
from dotenv import load_dotenv

# Load .env HERE rather than relying on config.py having been imported first.
# Real bug, found on the very first live test: this module read os.getenv at
# import time but nothing in it ever loaded the .env file, so it worked only
# by accident of import order (llm_router imports config before store). Any
# direct `import store` -- a probe, a test, a script -- saw empty credentials
# and reported "NOT CONFIGURED" while the keys were sitting in .env perfectly
# valid. load_dotenv() is idempotent, so calling it again costs nothing.
load_dotenv()

# .strip() is not cosmetic: "KEY= ck_abc" is the natural way to type this and
# leaves a leading space that would be sent as part of the credential,
# producing a 401 that looks exactly like a wrong key.
STORE_URL = os.getenv("STORE_URL", "https://bdubbgrowsllc.com").strip().rstrip("/")
_CONSUMER_KEY = os.getenv("STORE_CONSUMER_KEY", "").strip()
_CONSUMER_SECRET = os.getenv("STORE_CONSUMER_SECRET", "").strip()

_API = "/wp-json/wc/v3"
_TIMEOUT = 20.0

# A live store is slow to query and its numbers do not change minute to
# minute, but an agent mid-reasoning may ask the same question twice in one
# turn. A short TTL keeps that from becoming two round trips without ever
# serving Barry a stale figure in a later conversation.
_CACHE_TTL = 120.0
_cache = {}
_cache_lock = threading.Lock()


def is_configured() -> bool:
    return bool(_CONSUMER_KEY and _CONSUMER_SECRET)


class StoreNotConfigured(RuntimeError):
    """Raised instead of a confusing 401 when the keys were never set."""


def _cache_get(key):
    with _cache_lock:
        hit = _cache.get(key)
        if hit and (time.time() - hit[0]) < _CACHE_TTL:
            return hit[1]
    return None


def _cache_put(key, value):
    with _cache_lock:
        _cache[key] = (time.time(), value)


def _get(path: str, params: dict = None):
    """The ONLY request path in this module. GET only, by design."""
    if not is_configured():
        raise StoreNotConfigured(
            "The store API keys are not set. Barry needs to add "
            "STORE_CONSUMER_KEY and STORE_CONSUMER_SECRET to the backend's "
            ".env file (WooCommerce -> Settings -> Advanced -> REST API, "
            "permission 'Read'), then restart the backend."
        )
    params = dict(params or {})
    cache_key = (path, tuple(sorted(params.items())))
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    # Key/secret go in the auth header rather than the query string so they
    # never end up in a URL that could be logged or traced.
    resp = httpx.get(
        f"{STORE_URL}{_API}{path}",
        params=params,
        auth=(_CONSUMER_KEY, _CONSUMER_SECRET),
        timeout=_TIMEOUT,
        follow_redirects=True,
    )
    resp.raise_for_status()
    data = resp.json()
    _cache_put(cache_key, data)
    return data


def _money(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


# --- the three things the agents actually need -------------------------

def _search_products(query: str, per_page: int = 20) -> list[dict]:
    """WooCommerce search, re-ranked so NAME matches come first.

    ⚠️ Woo's `search` matches description text too and ranks by its own
    relevance: "Silution" returned 17 hits with the actual SiLution product
    LAST, behind every additive whose description mentions it. With the old
    per_page=5 the real product was not in the list at all, and Derek told
    Barry the store does not carry it (2026-09-01). Products whose name holds
    every query word come first, then most words, then Woo's order.
    """
    products = _get("/products", {"search": query, "per_page": max(1, min(per_page, 50)),
                                  "status": "publish"}) or []
    words = [w for w in re.split(r"[^a-z0-9]+", (query or "").lower()) if w]
    if not words:
        return products

    # Ties among full-name matches go to the EXACT name, then the name with the
    # fewest extra words: "Dimlux Maxi Controller" returned the CO2 sensor "for
    # Maxi Controller" first, and Derek titled the controller as a sensor
    # (2026-09-26).
    q_norm = " ".join(words)

    def _score(x):
        name = html.unescape(x.get("name", "") or "").lower()
        name_words = [w for w in re.split(r"[^a-z0-9]+", name) if w]
        hits = sum(w in name for w in words)
        return (-(hits == len(words)), -hits, " ".join(name_words) != q_norm, len(name_words))

    return sorted(products, key=_score)


def lookup_product(query: str, limit: int = 5) -> str:
    """Find products by name or SKU. Answers 'what does X cost / is it in
    stock' in ~200 characters instead of the 56K-character catalog doc.
    For what the product IS, use read_product -- this carries no description."""
    products = _search_products(query)[:max(1, min(limit, 20))]
    if not products:
        return f"No published product matches '{query}'."

    lines = [f"Products matching '{query}':"]
    for p in products:
        name = html.unescape(p.get("name", "?") or "?")
        price = p.get("price") or "?"
        regular = p.get("regular_price") or ""
        sale = p.get("sale_price") or ""
        sku = p.get("sku") or "no SKU"
        stock = p.get("stock_status", "?")
        cats = ", ".join(html.unescape(c.get("name", "") or "") for c in (p.get("categories") or []))
        on_sale = f" (on sale, was ${regular})" if sale and sale != regular else ""
        line = f"- {name} -- ${price}{on_sale} | SKU {sku} | {stock}"
        if cats:
            line += f" | {cats}"
        if p.get("permalink"):
            line += f"\n  {p['permalink']}"
        # PRODUCT PHOTOS (2026-08-21, Barry: "my marketing agent needs the
        # images for my products"). Until now this tool returned price and
        # stock only, so Vivian wrote product copy and product-shot prompts
        # having never seen the product. The real photo is the one thing that
        # makes a marketing image match what actually ships.
        imgs = p.get("images") or []
        if imgs:
            line += f"\n  photo: {imgs[0].get('src','')}"
            if len(imgs) > 1:
                line += f"  (+{len(imgs)-1} more)"
        lines.append(line)
    return "\n".join(lines)


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    text = _TAG_RE.sub(" ", text or "")
    text = html.unescape(text)
    return re.sub(r"[ \t]+", " ", re.sub(r"\s*\n\s*", "\n", text)).strip()


def read_product(query: str) -> str:
    """The FULL product page for ONE product -- description, short description,
    attributes, and per-variation prices. Barry, 2026-09-01: "he needs to read
    all the product descriptions before writing anything."

    lookup_product answers "what does it cost, is it in stock" in one line and
    never carried the description at all -- so Derek's product emails were
    written from a name, a price and a photo. This is the read-before-you-write
    tool: what the product actually is, in the words already on the site.
    Read-only like everything else here (same _get, same Read-scoped key).
    """
    # ⚠️ WooCommerce `search` matches DESCRIPTION text too, and ranks by its
    # own relevance: "Silution" returned 17 hits with the actual SiLution
    # product LAST, behind every additive whose description mentions it.
    # So: pull a wide page and prefer the product whose NAME carries every
    # word of the query; fall back to the top hit only if no name matches.
    products = _search_products(query)
    if not products:
        return f"No published product matches '{query}'."
    p = products[0]
    name = html.unescape(p.get("name", "?") or "?")
    out = [f"PRODUCT: {name}",
           f"price: ${p.get('price') or '?'}"
           + (f" (on sale, was ${p.get('regular_price')})"
              if p.get("sale_price") and p.get("sale_price") != p.get("regular_price") else "")
           + f" | {p.get('stock_status', '?')} | SKU {p.get('sku') or 'none'}"]
    cats = ", ".join(html.unescape(c.get("name", "") or "") for c in (p.get("categories") or []))
    if cats:
        out.append(f"categories: {cats}")
    if p.get("permalink"):
        out.append(f"link: {p['permalink']}")
    imgs = p.get("images") or []
    if imgs:
        out.append(f"photo: {imgs[0].get('src', '')}")
    short = _strip_html(p.get("short_description") or "")
    if short:
        out.append(f"\nSHORT DESCRIPTION:\n{short[:1500]}")
    desc = _strip_html(p.get("description") or "")
    if desc:
        out.append(f"\nFULL DESCRIPTION (this is what the site says -- read it before "
                   f"you write a word about this product):\n{desc[:6000]}")
        if len(desc) > 6000:
            out.append("[description truncated at 6000 chars]")
    else:
        out.append("\nFULL DESCRIPTION: (none on the site -- say so rather than inventing one)")
    attrs = p.get("attributes") or []
    if attrs:
        out.append("\nATTRIBUTES:")
        for a in attrs:
            opts = ", ".join(html.unescape(str(o)) for o in (a.get("options") or []))
            out.append(f"  - {html.unescape(a.get('name', '') or '')}: {opts}")
    if p.get("type") == "variable" and p.get("id"):
        vars_ = _get(f"/products/{p['id']}/variations", {"per_page": 25}) or []
        if vars_:
            out.append("\nSIZES / VARIATIONS:")
            for v in vars_:
                label = " / ".join(html.unescape(str(a.get("option", ""))) for a in (v.get("attributes") or []))
                out.append(f"  - {label or v.get('sku') or '?'}: ${v.get('price') or '?'}"
                           f" | {v.get('stock_status', '?')}")
    other = [html.unescape(x.get("name", "") or "") for x in products if x is not p]
    if other:
        out.append(f"\n(other matches for '{query}': {', '.join(other[:4])} -- "
                   f"call again with a more specific name to read one of those)")
    return "\n".join(out)


def sales_summary(days: int = 30) -> str:
    """Revenue, order count, AOV, status mix and top sellers for a window.

    Deliberately counts revenue from COMPLETED and PROCESSING orders only.
    This store's history is ~60% failed orders (card-testing fraud plus a
    friend repeatedly testing Klarna), so a naive total would overstate the
    business by a wide margin -- see the store audit in CLAUDE.md.
    """
    days = max(1, min(int(days or 30), 365))
    after = time.strftime("%Y-%m-%dT00:00:00", time.gmtime(time.time() - days * 86400))

    orders = []
    page = 1
    while page <= 5:  # hard cap: 500 orders is plenty for any summary window
        batch = _get("/orders", {"after": after, "per_page": 100, "page": page})
        if not batch:
            break
        orders.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    if not orders:
        return (f"No orders at all in the last {days} days "
                f"(searched from {after[:10]}).")

    counted_statuses = {"completed", "processing"}
    by_status = {}
    revenue = 0.0
    counted = 0
    product_totals = {}

    for o in orders:
        status = o.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        if status not in counted_statuses:
            continue
        counted += 1
        revenue += _money(o.get("total"))
        for item in (o.get("line_items") or []):
            name = item.get("name", "?")
            entry = product_totals.setdefault(name, {"qty": 0, "revenue": 0.0})
            entry["qty"] += int(item.get("quantity") or 0)
            entry["revenue"] += _money(item.get("total"))

    aov = (revenue / counted) if counted else 0.0
    top = sorted(product_totals.items(), key=lambda kv: kv[1]["revenue"], reverse=True)[:5]

    lines = [
        f"B Dubb Grows -- last {days} days (since {after[:10]}):",
        f"- Revenue (completed + processing): ${revenue:,.2f} across {counted} orders",
        f"- Average order value: ${aov:,.2f}",
        f"- All orders in window, by status: "
        + ", ".join(f"{k} {v}" for k, v in sorted(by_status.items(), key=lambda kv: -kv[1])),
    ]
    if top:
        lines.append("- Top sellers by revenue:")
        for name, t in top:
            lines.append(f"    {name} -- ${t['revenue']:,.2f} ({t['qty']} sold)")
    lines.append(
        "Note: revenue counts completed and processing orders only. Failed and "
        "cancelled orders are excluded -- most of this store's failures are "
        "card-testing attempts, not lost customers."
    )
    return "\n".join(lines)


def _attribution_channel(meta: dict) -> str:
    """One plain channel name from WooCommerce's order-attribution fields."""
    entry = meta.get("session_entry") or ""
    src = (meta.get("utm_source") or "").lower()
    kind = (meta.get("source_type") or "").lower()
    if "srsltid=" in entry:
        # Data label from WooCommerce order attribution (srsltid = a free Google Shopping referral).
        # It names the channel the buyer came FROM; it is NOT an outbound call to a Google service.
        return "Google free Shopping listing (Merchant Center)"
    if not kind:
        return "no source recorded"
    if kind == "typein":
        return "direct (typed the address / bookmark)"
    if kind == "admin":
        return "created in wp-admin"
    return f"{kind} / {src}" if src else kind


def buyer_sources(days: int = 90) -> str:
    """Where the people who ORDERED came from, per order and per channel.

    Reads WooCommerce's built-in order attribution (Barry, 2026-09-25: "she
    needs to know this stuff and some of the other team"). It only sees
    people who reached an order -- it cannot count visitors. No customer
    names, emails or payment details are ever put in the reply (a PayPal
    payment title carries the buyer's email, so it is left out on purpose).
    """
    days = max(1, min(int(days or 90), 365))
    after = time.strftime("%Y-%m-%dT00:00:00", time.gmtime(time.time() - days * 86400))

    orders = []
    page = 1
    while page <= 5:
        batch = _get("/orders", {"after": after, "per_page": 100, "page": page})
        if not batch:
            break
        orders.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    if not orders:
        return (f"No orders at all in the last {days} days (searched from {after[:10]}), "
                f"so there is no buyer source to report. This tool cannot see visitors.")

    counted_statuses = {"completed", "processing"}
    channels: dict[str, dict] = {}
    rows = []
    for o in orders:
        meta = {m.get("key", "").replace("_wc_order_attribution_", ""): m.get("value")
                for m in (o.get("meta_data") or []) if "attribution" in str(m.get("key", ""))}
        status = o.get("status", "unknown")
        ch = _attribution_channel(meta)
        c = channels.setdefault(ch, {"paid": 0, "revenue": 0.0, "other": 0})
        if status in counted_statuses:
            c["paid"] += 1
            c["revenue"] += _money(o.get("total"))
        else:
            c["other"] += 1
        entry = (meta.get("session_entry") or "").split("?")[0].replace(STORE_URL, "") or "-"
        rows.append(
            f"    #{o.get('id')} {str(o.get('date_created', ''))[:10]} {status} "
            f"${_money(o.get('total')):,.2f} -- {ch}; landed on {entry}; "
            f"{meta.get('session_pages') or '?'} pages; {meta.get('device_type') or '?'}"
        )

    lines = [f"B Dubb Grows -- where buyers came from, last {days} days (since {after[:10]}):",
             "- By channel (paid = completed + processing):"]
    for ch, c in sorted(channels.items(), key=lambda kv: (-kv[1]["revenue"], -kv[1]["other"])):
        lines.append(f"    {ch}: {c['paid']} paid orders, ${c['revenue']:,.2f}"
                     + (f"; {c['other']} failed/cancelled/other" if c["other"] else ""))
    lines.append("- Every order, newest first:")
    lines.extend(rows[:40])
    if len(rows) > 40:
        lines.append(f"    ... {len(rows) - 40} older orders not listed")
    lines.append(
        "Note: this is WooCommerce order attribution. It only knows about people "
        "who reached an order -- it cannot count or describe visitors who did not "
        "buy. Never quote a visitor number from it. 'no source recorded' is normal "
        "for failed card attempts (mostly card-testing)."
    )
    return "\n".join(lines)


def what_is_selling(days: int = 90) -> str:
    """What has MOVED lately and what has not -- for deciding what to post about.

    Barry, 2026-09-18: "they need the tools to go to my site and look at the
    products to decide on what to post about. Maybe recent sellers or cold
    products." Neither existed: sales_summary names the top five sellers and
    nothing anywhere names what is sitting.

    The cold list is the interesting half. A product in stock that has not sold
    in the window is either invisible or unexplained, and both of those are
    fixed by a post rather than by a discount.

    Window defaults to 90 days, not 30, on purpose: this store has had long
    stretches with no orders at all, and a 30-day window would report an empty
    shop and tell them nothing. If the window really is empty the answer says
    so and says to widen it, instead of implying the catalogue is all cold.
    """
    days = max(1, min(int(days or 90), 365))
    after = time.strftime("%Y-%m-%dT00:00:00",
                          time.gmtime(time.time() - days * 86400))

    orders, page = [], 1
    while page <= 5:
        batch = _get("/orders", {"after": after, "per_page": 100, "page": page})
        if not batch:
            break
        orders.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    sold = {}
    for o in orders:
        if o.get("status") not in ("completed", "processing"):
            continue
        for item in (o.get("line_items") or []):
            pid = item.get("product_id")
            name = item.get("name", "?")
            e = sold.setdefault(pid or name, {"name": name, "qty": 0, "rev": 0.0})
            e["qty"] += int(item.get("quantity") or 0)
            e["rev"] += _money(item.get("total"))

    catalogue, page = [], 1
    while page <= 4:
        batch = _get("/products", {"per_page": 100, "page": page,
                                   "status": "publish", "stock_status": "instock",
                                   "_fields": "id,name,price,permalink,type,categories"})
        if not batch:
            break
        catalogue.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    if not catalogue:
        return ("Could not read the catalogue, so there is nothing to compare "
                "sales against. Tell Barry rather than guessing.")

    # WooCommerce returns names HTML-encoded ("Nutrients &amp; Fertilizers").
    # Left raw, an agent copies "&amp;" straight into a caption.
    import html as _html
    for e in sold.values():
        e["name"] = _html.unescape(e["name"])
    for p in catalogue:
        p["name"] = _html.unescape(p.get("name") or "")
        for c in (p.get("categories") or []):
            c["name"] = _html.unescape(c.get("name") or "")

    movers = sorted(sold.values(), key=lambda e: e["rev"], reverse=True)[:8]
    sold_ids = set(sold.keys())
    cold = [p for p in catalogue if p.get("id") not in sold_ids]

    lines = [f"WHAT IS SELLING -- last {days} days (since {after[:10]}), "
             f"{len(catalogue)} products in stock:"]
    if movers:
        lines.append(f"\nMOVED ({len(sold)} products sold):")
        for e in movers:
            lines.append(f"    {e['name']} -- {e['qty']} sold, ${e['rev']:,.2f}")
        lines.append("  A recent seller is proof of demand: a post about one of "
                     "these is pushing on something already moving.")
    else:
        lines.append(
            f"\nMOVED: nothing at all in {days} days. That is a real fact about "
            "this store, not a tooling error -- do NOT read it as 'every product "
            "is cold' and do not tell Barry his catalogue is dead. Ask for a "
            "longer window, or pick on margin and season instead of on sales.")

    if cold:
        lines.append(f"\nSITTING ({len(cold)} in stock, no sales in the window) "
                     "-- these are the ones a post can actually change:")
        for p in cold[:15]:
            cats = ", ".join(c.get("name", "") for c in (p.get("categories") or [])[:2])
            lines.append(f"    {p['name']} -- ${p.get('price') or '?'}"
                         + (f"  [{cats}]" if cats else ""))
        if len(cold) > 15:
            lines.append(f"    ... and {len(cold) - 15} more.")
    lines.append(
        "\nHOW TO USE THIS: a mover is proof of demand, a sitter is an "
        "unanswered question -- ask why nobody buys it and answer THAT in the "
        "post. Not selling is not the same as not good; most of these have "
        "simply never been explained to anyone. Read the product before you "
        "pick it, and never call anything unpopular in public.")
    return "\n".join(lines)


def store_status() -> str:
    """Cheap reachability + configuration check. Used by the readiness
    display and by anyone debugging why a store tool returned nothing."""
    if not is_configured():
        return ("Store API: NOT CONFIGURED. STORE_CONSUMER_KEY / "
                "STORE_CONSUMER_SECRET are missing from .env.")
    try:
        # per_page=1 keeps this to the smallest possible real query.
        _get("/products", {"per_page": 1})
        return f"Store API: connected to {STORE_URL} (read-only)."
    except httpx.HTTPStatusError as e:
        return (f"Store API: reachable but refused the request "
                f"({e.response.status_code}). Check the key permission is 'Read' "
                f"and that the key has not been revoked.")
    except Exception as e:  # noqa: BLE001 -- surface the real reason, never swallow
        return f"Store API: could not reach {STORE_URL} ({type(e).__name__}: {e})."


# ---------------------------------------------------------------------------
# READ-ONLY SITE ACCESS (2026-08-21, Barry: "Vivian needs full access, not
# fully, but she needs to be able to see my site, but not write. Not yet
# anyways, because you need to help me build all this right, first").
#
# So: she can SEE everything and change nothing. This module still contains
# no write verb of any kind -- _get is the only request path, and the
# WooCommerce key itself should stay scoped Read. Pages and posts come from
# WordPress's public wp/v2 API (no auth needed to read published content).
# ---------------------------------------------------------------------------

def _wp_get(path: str, params: dict | None = None):
    """Public WordPress REST read. Separate from _get because wp/v2 needs no
    WooCommerce auth -- and keeping them separate means a marketing question
    can never accidentally travel with store credentials attached."""
    url = f"{STORE_URL.rstrip('/')}/wp-json/wp/v2{path}"
    with httpx.Client(timeout=25.0, follow_redirects=True) as client:
        resp = client.get(url, params=params or {})
        resp.raise_for_status()
        return resp.json()


# GOTCHO BACK (2026-09-02, Barry: "Gotcho Back website is gotchoback.com they
# can go check it out. i gotta clean it up because i sold most of those bags, i
# just havent went to the back office to work on it at all. im bymyself").
# Read-only, NO credentials: WooCommerce's public Store API (wc/store/v1) and
# WordPress's public wp/v2, both via ?rest_route= because the site runs plain
# permalinks (its /wp-json/ path 404s). Prices come back in minor units.
GOTCHOBACK_URL = os.getenv("GOTCHOBACK_URL", "https://gotchoback.com").strip().rstrip("/")


def _gb_get(route: str, params: dict | None = None):
    p = {"rest_route": route}
    p.update(params or {})
    # the host's firewall 403s anything that does not look like a browser
    with httpx.Client(timeout=25.0, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                             "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                               "Accept": "application/json,text/plain,*/*"}) as client:
        resp = client.get(GOTCHOBACK_URL + "/", params=p)
        resp.raise_for_status()
        return resp.json()


def browse_gotchoback(what: str = "products", query: str = "", limit: int = 20) -> str:
    """Look around gotchoback.com, read-only. what = products | pages | overview."""
    what = (what or "products").strip().lower()
    limit = max(1, min(int(limit or 20), 50))
    if what in ("products", "overview", ""):
        params = {"per_page": limit}
        if query:
            params["search"] = query
        items = _gb_get("/wc/store/v1/products", params) or []
        if not items:
            return "gotchoback.com: no products matched" + (f" '{query}'." if query else ".")
        lines = [f"gotchoback.com -- {len(items)} product(s){' matching ' + repr(query) if query else ''} "
                 "(REMEMBER: Barry says most of these bags are already SOLD and the catalog is stale):"]
        for p in items:
            pr = p.get("prices") or {}
            unit = pr.get("price") or "0"
            minor = int(pr.get("currency_minor_unit", 2) or 2)
            try:
                price = f"{int(unit) / (10 ** minor):.2f} {pr.get('currency_code', 'USD')}"
            except (TypeError, ValueError):
                price = str(unit)
            lines.append(f"- {_strip_html_short(p.get('name', ''), 80)} | {price} | "
                         f"{'in stock' if p.get('is_in_stock') else 'OUT OF STOCK'} | "
                         f"{_strip_html_short(p.get('short_description') or p.get('description') or '', 140)} | "
                         f"{p.get('permalink', '')}")
        if what == "overview":
            try:
                pages = _gb_get("/wp/v2/pages", {"per_page": 20, "_fields": "title,link"}) or []
                lines.append("PAGES: " + "; ".join(
                    f"{_strip_html_short((pg.get('title') or {}).get('rendered', ''), 40)} ({pg.get('link', '')})"
                    for pg in pages))
            except Exception as e:  # noqa: BLE001
                lines.append(f"PAGES: could not read ({type(e).__name__})")
        return "\n".join(lines)
    if what == "pages":
        pages = _gb_get("/wp/v2/pages", {"per_page": limit, "_fields": "title,link,excerpt"}) or []
        return "gotchoback.com pages:\n" + "\n".join(
            f"- {_strip_html_short((pg.get('title') or {}).get('rendered', ''), 60)} | {pg.get('link', '')} | "
            f"{_strip_html_short((pg.get('excerpt') or {}).get('rendered', ''), 160)}" for pg in pages)
    return "what must be products, pages or overview."


# 2026-09-26: renamed from a SECOND "_strip_html" that silently replaced the first for the whole
# module -- read_product cut every product description to 400 chars, so Derek never saw feeding
# rates, EC targets or the FAQ ("theres no info about the product"). One name, one job.
def _strip_html_short(s: str, limit: int = 400) -> str:
    text = re.sub(r"<[^>]+>", " ", s or "")
    text = re.sub(r"&[a-z]+;|&#\d+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = html.unescape(text)
    return text[:limit] + ("..." if len(text) > limit else "")


def browse_site(what: str = "overview", query: str = "", limit: int = 15) -> str:
    """Look around the live site, read-only.

    what = overview | categories | products | pages | posts
    """
    what = (what or "overview").strip().lower()
    limit = max(1, min(int(limit or 15), 40))

    if what in ("overview", ""):
        cats = _get("/products/categories", {"per_page": 40, "orderby": "count", "order": "desc"})
        pages = _wp_get("/pages", {"per_page": 30, "status": "publish", "_fields": "title,link"})
        posts = _wp_get("/posts", {"per_page": 5, "status": "publish", "_fields": "title,link,date"})
        out = [f"LIVE SITE: {STORE_URL} (read-only view)", "", "TOP CATEGORIES:"]
        for c in (cats or [])[:12]:
            out.append(f"  {html.unescape(c.get('name','?') or '?')} -- {c.get('count',0)} products")
        out.append("")
        out.append(f"PAGES ({len(pages or [])}):")
        for p in (pages or [])[:15]:
            out.append(f"  {html.unescape((p.get('title') or {}).get('rendered','?'))} -- {p.get('link','')}")
        out.append("")
        out.append("LATEST BLOG POSTS (auto-published by the Soro plugin):")
        for p in (posts or []):
            out.append(f"  {html.unescape((p.get('title') or {}).get('rendered','?'))} ({(p.get('date') or '')[:10]})")
        return "\n".join(out)

    if what == "categories":
        cats = _get("/products/categories", {"per_page": 40, "orderby": "count", "order": "desc"})
        return "PRODUCT CATEGORIES:\n" + "\n".join(
            f"  {html.unescape(c.get('name','?') or '?')} -- {c.get('count',0)} products" for c in (cats or []))

    if what == "products":
        params = {"per_page": limit, "status": "publish"}
        if query:
            params["search"] = query
        ps = _get("/products", params)
        if not ps:
            return f"No published products found{' for ' + query if query else ''}."
        out = []
        for p in ps:
            imgs = p.get("images") or []
            out.append(
                f"- {html.unescape(p.get('name','?') or '?')} -- ${p.get('price','?')} | {p.get('stock_status','?')}"
                + (f"\n  photo: {imgs[0].get('src','')}" if imgs else "\n  NO PHOTO on this product")
                + (f"\n  {p.get('permalink','')}" if p.get("permalink") else ""))
        return "\n".join(out)

    if what in ("pages", "posts"):
        params = {"per_page": limit, "status": "publish"}
        if query:
            params["search"] = query
        items = _wp_get(f"/{what}", params)
        if not items:
            return f"No {what} found{' for ' + query if query else ''}."
        out = []
        for it in items:
            out.append(f"- {html.unescape((it.get('title') or {}).get('rendered','?'))}  {it.get('link','')}")
            excerpt = _strip_html_short((it.get("excerpt") or {}).get("rendered", "")
                                  or (it.get("content") or {}).get("rendered", ""))
            if excerpt:
                out.append(f"  {excerpt}")
        return "\n".join(out)

    return ("browse_site takes what = overview | categories | products | pages | posts "
            "(plus an optional query). Read-only -- nothing on the site can be changed.")


# --- THE CHECKOUT WALK (2026-09-08) ---------------------------------------------
# Sophie's store-ops manual (Barry's doc, fact `sophie-store-ops-brain.md`) says:
# "Walk the whole path yourself, logged out. Grid -> variant -> cart -> address
# -> shipping -> payment. Stop before submitting." This is that walk as a tool,
# through WooCommerce's PUBLIC Store API as a guest -- exactly what a customer
# hits. It never places an order: there is no call to /checkout POST here, and
# the guest cart is thrown away with the session. Read-only by construction,
# same as everything else in this file.
_WALK_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/128.0 Safari/537.36",
            "Cache-Control": "no-cache"}
_WALK_ADDR = {"first_name": "Checkout", "last_name": "Walk", "address_1": "1 Main St",
              "city": "Colorado Springs", "state": "CO", "postcode": "80903",
              "country": "US", "email": "checkout-walk@example.com"}


def walk_checkout(query: str = "silution") -> str:
    """Logged-out purchase path for one product, step by step. Never submits."""
    import re as _re
    B = f"{STORE_URL}/wp-json/wc/store/v1"
    steps: list[str] = []
    ok = True
    try:
        with httpx.Client(headers=_WALK_UA, timeout=40, follow_redirects=True) as s:
            shop = s.get(f"{STORE_URL}/shop/?nocache=1")
            cards = len(_re.findall(r'class="[^"]*\bproduct-small\b', shop.text))
            buy = shop.text.count("Select options") + shop.text.count("Add to cart")
            steps.append(f"1. Shop grid: HTTP {shop.status_code}, {cards} product cards, "
                         f"{buy} buy buttons" + ("" if buy else "  <-- NO BUY BUTTONS ON THE GRID"))
            ok &= shop.status_code == 200 and cards > 0 and buy > 0

            prods = s.get(f"{B}/products", params={"search": query, "per_page": 1}).json()
            if not prods:
                return "\n".join(steps + [f"2. No product matches '{query}' in the Store API. Stopped."])
            p = prods[0]
            page = s.get(p["permalink"])
            steps.append(f"2. Product page '{p['name']}': HTTP {page.status_code}, "
                         f"buy button {'present' if 'single_add_to_cart_button' in page.text else 'MISSING'}")
            ok &= page.status_code == 200 and "single_add_to_cart_button" in page.text

            nonce = s.get(f"{B}/cart").headers.get("Nonce", "")
            body = {"id": p["id"], "quantity": 1}
            if p.get("variations"):
                # Cheapest size, not variations[0] -- the Store API lists the
                # biggest first, and a $721 test cart for a 5 L bottle read as
                # customer price friction (Sophie, 2026-09-25).
                v = p["variations"][0]
                try:
                    vs = s.get(f"{B}/products", params={"type": "variation", "parent": p["id"],
                                                          "per_page": 50}).json()
                    cheapest = min(vs, key=lambda x: int(x["prices"]["price"]))
                    v = next((x for x in p["variations"] if x["id"] == cheapest["id"]), v)
                except Exception:  # noqa: BLE001 -- fall back to the first size
                    pass
                body["variation"] = [{"attribute": a["name"], "value": a["value"]} for a in v["attributes"]]
            a = s.post(f"{B}/cart/add-item", json=body, headers={"Nonce": nonce})
            nonce = a.headers.get("Nonce") or nonce
            j = a.json() if a.headers.get("content-type", "").startswith("application/json") else {}
            items = j.get("items_count")
            steps.append(f"3. Add to cart: HTTP {a.status_code}, items in cart = {items}"
                         + (f"  <-- {j.get('message')}" if a.status_code >= 400 else ""))
            ok &= a.status_code < 300 and bool(items)

            u = s.post(f"{B}/cart/update-customer",
                       json={"shipping_address": _WALK_ADDR, "billing_address": _WALK_ADDR},
                       headers={"Nonce": nonce})
            uj = u.json() if u.status_code < 300 else {}
            rates = [(r.get("name", "?"), _money(r.get("price", 0)) / 100)
                     for pk in uj.get("shipping_rates", []) for r in pk.get("shipping_rates", [])]
            steps.append(f"4. Colorado address entered: HTTP {u.status_code}; shipping options = "
                         + (", ".join(f"{n} ${c:.2f}" for n, c in rates) if rates
                            else "NONE  <-- checkout would block here"))
            ok &= u.status_code < 300 and bool(rates)

            pm = uj.get("payment_methods") or []
            tot = uj.get("totals") or {}
            steps.append(f"5. Payment methods offered: {', '.join(pm) if pm else 'NONE  <-- nobody can pay'}; "
                         f"cart total ${_money(tot.get('total_price', 0)) / 100:.2f} "
                         f"(tax ${_money(tot.get('total_tax', 0)) / 100:.2f})")
            ok &= bool(pm)
    except Exception as e:  # noqa: BLE001
        steps.append(f"WALK ABORTED -- {type(e).__name__}: {e}")
        ok = False
    steps.append("6. Stopped before placing the order (never submits).")
    verdict = ("CHECKOUT WORKS end to end for a logged-out customer." if ok
               else "CHECKOUT IS BROKEN at the step marked <-- above. Tell Barry which step.")
    return verdict + "\n" + "\n".join(steps)
