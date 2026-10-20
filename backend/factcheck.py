"""
factcheck -- MECHANICAL truth checks on outbound marketing text (2026-09-09).

WHY (Barry, 2026-09-09): "Derek sent out an email that wasnt true... he said we
have microlife in, but we dont. Its still out." -> "he should only post real
stuff and only for whats there, dont make up shit."

What happened: cadence email #207 ("Fall is here...") was drafted with ZERO tool
calls (trace 2026-09-07T18:12, tool_calls []) even though the brief said to
read_product every product. It claimed Bionova MicroLife was "finally back in
stock" (it is outofstock), a "GrowMax Water Filter cartridge" was back in stock
(no such product), a "new guide" was published (unverified), and a "ten-to-
twenty percent" feed boost (invented). It was approved and sent to customers.
A prompt rule failed; per the house rule, the check is now code.

This module never calls a model. It reads the LIVE store (products + stock +
recent posts) and compares against the text:

  PROBLEMS (block):
    - a catalog product described as in stock / back in stock / restocked while
      the store says it is not in stock
    - "<Something> is back in stock" where <Something> is not a product we carry
    - a "new guide / post / article" claim with no link to a real recent post
  WARNINGS (reported, not blocking on their own):
    - percentages and dollar figures that are not a known offer or a live price

Used by email_cadence (send the draft back to Derek once with the report, then
banner it) and by dispatch (refuse to send anything that fails NOW -- stock can
change between draft and send day). Offline Mode / unconfigured store: the
check cannot run and says so; callers treat that as "not verified", never as
"passed".
"""
from __future__ import annotations

import html
import re

import store

BANNER = "[OFFICE FACT-CHECK FAILED -- DO NOT SEND AS-IS]"

_STOCK_PHRASE_RE = re.compile(
    r"\b(?:back\s+in\s+stock|in\s+stock|restock(?:ed|s)?|re-?stocked|now\s+available|"
    r"available\s+(?:now|again)|just\s+(?:arrived|landed|got|hit)|back\s+on\s+the\s+shelf|"
    r"finally\s+back|is\s+back|are\s+back)\b", re.I)
_UNKNOWN_STOCK_RE = re.compile(
    r"(?:^|[.!?\n]\s*|\bthe\s+|\bour\s+)((?:[A-Z][\w'&\-]*\s+){0,4}[A-Z][\w'&\-]*)"
    r"(?:\s+(?:cartridge|bottle|kit|pack|set|bundle))?\s+(?:is|are)\s+(?:also\s+|finally\s+)?"
    r"(?:back\s+in\s+stock|in\s+stock|restocked|back\s+on\s+the\s+shelf)", re.I)
_GUIDE_CLAIM_RE = re.compile(
    r"\b(?:new|just\s+published|published|latest|fresh|posted)\s+(?:\w+\s+){0,2}"
    r"(?:guide|post|article|blog(?:\s+post)?|write-?up|tutorial)\b", re.I)
_NEGATION_RE = re.compile(
    r"\b(?:isn'?t|is\s+not|aren'?t|are\s+not|wasn'?t|was\s+not|not\s+yet|still\s+(?:out|on\s+order|"
    r"waiting)|correction|mistake|wrong|error|apolog)", re.I)
_PRE_NEGATION_RE = re.compile(r"\b(?:not|isn'?t|never|no\s+longer)\s+(?:\w+\s+){0,2}$", re.I)
_SALE_PHRASE_RE = re.compile(r"(?:on\s+sale|marked\s+down|price\s+drop|discounted|reduced\s+price|now\s+\$)", re.I)
_URL_RE = re.compile(r"https?://[^\s\"'<>)]+", re.I)
_PCT_RE = re.compile(r"\b(\d{1,3})\s*(?:%|percent)\b|\b(ten|fifteen|twenty|twenty-five|thirty|forty|fifty)(?:-to-\w+)?\s+percent\b", re.I)
_DOLLAR_RE = re.compile(r"\$\s?(\d{1,5}(?:\.\d{2})?)")

# Words too generic to identify a product on their own.
_GENERIC = {
    "bionova", "line", "soil", "enhancer", "nutrients", "nutrient", "fertilizer",
    "fertilizers", "organic", "granular", "liquid", "all-in-one", "vegan", "universal",
    "premium", "grow", "growing", "plant", "plants", "light", "lights", "led", "tent",
    "tents", "kit", "kits", "set", "pack", "bottle", "gallon", "liter", "litre", "quart",
    "base", "bloom", "veg", "growth", "booster", "supplement", "additive", "with", "and",
    "for", "the", "of", "in", "x", "ft", "inch", "digital", "meter", "pump", "filter",
    "system", "hydroponic", "hydroponics", "indoor", "garden", "gardening", "series",
    "pro", "plus", "max", "mini", "large", "small", "medium", "black", "white", "green",
    "temperature", "camera", "water", "filter", "filters", "replacement", "housing",
    "wrench", "membrane", "controller", "humidity", "carbon", "sediment", "block",
    "reverse", "osmosis", "booster", "filtration", "infra-red", "infrared", "long",
    "short", "meters", "system", "systems", "power", "timer", "fan", "fans", "duct",
    "ducting", "clip", "clips", "tray", "trays", "mat", "mats", "heat", "seedling",
    "nutrition", "flower", "flowering", "mineral", "minerals", "hydro", "coco", "soil",
    "root", "roots", "leaf", "leaves", "starter", "complete", "advanced", "natural",
}
KNOWN_OFFER_PCTS = {10, 15}          # BIG10 / BIG15
KNOWN_OFFER_DOLLARS = {200.0, 10.0}  # free shipping over $200 / $10 flat


def _aliases(name: str) -> set[str]:
    """Distinctive lowercase tokens that identify a product in prose."""
    clean = re.sub(r"[^\w\s'&\-]", " ", html.unescape(name or "")).lower()
    words = [w for w in re.split(r"\s+", clean) if w]
    out = {clean.strip()}
    for w in words:
        if len(w) >= 7 and w not in _GENERIC and not w.isdigit():
            out.add(w)
    # two-word chunks (e.g. "crop defender", "cali pro")
    for a, b in zip(words, words[1:]):
        if a not in _GENERIC or b not in _GENERIC:
            if len(a) >= 3 and len(b) >= 2 and not (a in _GENERIC and b in _GENERIC):
                out.add(f"{a} {b}")
    return {x for x in out if len(x) >= 5}


def _catalog() -> list[dict]:
    """Every published product with its live stock status (3 pages max)."""
    prods: list[dict] = []
    for page in (1, 2, 3):
        batch = store._get("/products", {"per_page": 100, "page": page, "status": "publish",
                                         "_fields": "id,name,type,price,regular_price,sale_price,on_sale,stock_status,permalink"})
        if not batch:
            break
        prods.extend(batch)
        if len(batch) < 100:
            break
    return prods


def _recent_posts(limit: int = 40) -> list[dict]:
    return store._wp_get("/posts", {"per_page": limit, "status": "publish",
                                     "_fields": "title,link,date"}) or []


def check_email(text: str) -> dict:
    """Return {"ok", "verified", "problems", "warnings", "checked"}.

    verified=False means the store could not be read (offline, keys, error) --
    nothing was proven either way and callers must NOT treat it as a pass."""
    plain = re.sub(r"<[^>]+>", " ", text or "")
    plain = html.unescape(re.sub(r"\s+", " ", plain))
    low = plain.lower()
    result = {"ok": False, "verified": False, "problems": [], "warnings": [], "checked": []}

    if not store.is_configured():
        result["problems"].append("store keys not set -- claims could not be verified")
        return result
    try:
        import memory
        if memory.is_offline_mode():
            result["problems"].append("Offline Mode is on -- stock could not be verified")
            return result
    except Exception:
        pass
    try:
        catalog = _catalog()
    except Exception as exc:  # noqa: BLE001
        result["problems"].append(f"could not read the store: {exc}")
        return result
    result["verified"] = True

    prices = set()
    for p in catalog:
        try:
            prices.add(round(float(p.get("price") or 0), 2))
        except (TypeError, ValueError):
            pass

    # 1. Catalog products mentioned + any stock claim near them.
    mentioned: list[tuple[dict, int]] = []
    for p in catalog:
        name = html.unescape(p.get("name") or "")
        for alias in _aliases(name):
            m = re.search(r"(?<![\w-])" + re.escape(alias) + r"(?![\w-])", low)
            if m:
                mentioned.append((p, m.start()))
                break
    try:
        posts = _recent_posts()
    except Exception:
        posts = []
    post_titles = [html.unescape((q.get("title") or {}).get("rendered", "")).lower()
                   for q in posts]
    # Match on the first five words of a title: emails shorten titles
    # ("Bionova Premium Fertilizer on Sale" for "...on Sale for Growers").
    post_titles = [" ".join(t.split()[:5]) for t in post_titles if t]
    post_titles = [t for t in post_titles if len(t) >= 12]
    seen = set()
    for p, idx in mentioned:
        if p["id"] in seen:
            continue
        seen.add(p["id"])
        window = low[max(0, idx - 160): idx + 200]
        status = p.get("stock_status") or "?"
        on_sale = bool(p.get("on_sale"))
        # VARIATIONS (learned on #230: "25 kg Profimix back in stock" was TRUE --
        # the 25 kg variation was instock while the 2 kg was out, and $307.95
        # was the 25 kg price). A claim about a variable product is judged
        # against its variations too.
        if p.get("type") == "variable":
            try:
                vs = store._get(f"/products/{p['id']}/variations", {"per_page": 25}) or []
            except Exception:
                vs = []
            if any(v.get("stock_status") == "instock" for v in vs):
                status = "instock"
            on_sale = on_sale or any(v.get("on_sale") for v in vs)
            for v in vs:
                try:
                    prices.add(round(float(v.get("price") or 0), 2))
                except (TypeError, ValueError):
                    pass
        claim = _STOCK_PHRASE_RE.search(window)
        # A NEGATED claim is not a claim: "I said it was back in stock. It
        # isn't" (the correction email) must pass. Look right after the phrase
        # and right before it for a denial.
        if claim and (_NEGATION_RE.search(window[claim.end(): claim.end() + 90])
                      or _PRE_NEGATION_RE.search(window[max(0, claim.start() - 40): claim.start()])):
            claim = None
        result["checked"].append(f"{html.unescape(p['name'])}: {status}"
                                 + (f" (text says '{claim.group(0)}')" if claim else ""))
        if claim and status != "instock":
            result["problems"].append(
                f"'{html.unescape(p['name'])}' is described as '{claim.group(0)}' but the "
                f"store says {status.upper()}")
        # "on sale" / "% off" / "discounted" near a product that is NOT on sale
        # is the same class of lie as a stock claim (added after #230's subject
        # "Bionova Premium Fertilizer on Sale" -- verified true, but unchecked).
        sale_claim = _SALE_PHRASE_RE.search(window)
        # ...unless the phrase is part of a real post title he linked
        # ("Bionova Premium Fertilizer on Sale" is a blog post, #230).
        if sale_claim and any(t and t in window for t in post_titles):
            sale_claim = None
        if sale_claim and not on_sale:
            result["problems"].append(
                f"'{html.unescape(p['name'])}' is described as '{sale_claim.group(0)}' but the "
                f"store does not have it on sale")

    # 2. "<X> is back in stock" where X is nothing we carry.
    all_aliases = set()
    for p in catalog:
        all_aliases |= _aliases(html.unescape(p.get("name") or ""))
    for m in _UNKNOWN_STOCK_RE.finditer(plain):
        subject = m.group(1).strip()
        sl = subject.lower()
        if len(sl) < 4 or sl in ("it", "this", "that", "they", "we", "everything", "stock"):
            continue
        if not any(a in sl or sl in a for a in all_aliases):
            result["problems"].append(
                f"'{subject}' is described as in stock but is not a product the store carries")

    # 3. "new guide / post" claims need a real recent post link.
    if _GUIDE_CLAIM_RE.search(plain):
        urls = set(_URL_RE.findall(text or ""))
        post_links = {(p.get("link") or "").rstrip("/") for p in posts}
        if not any(u.rstrip("/") in post_links for u in urls):
            titles = "; ".join(html.unescape((p.get("title") or {}).get("rendered", ""))
                               for p in posts[:5])
            result["problems"].append(
                "claims a new guide/post but links no real published post"
                + (f" (recent real posts: {titles})" if titles else ""))

    # 4. Numbers that are not a known offer or a live price (variation prices
    # were added to `prices` while checking mentions above).
    words = {"ten": 10, "fifteen": 15, "twenty": 20, "twenty-five": 25, "thirty": 30,
             "forty": 40, "fifty": 50}
    for m in _PCT_RE.finditer(plain):
        n = int(m.group(1)) if m.group(1) else words.get((m.group(2) or "").lower(), None)
        if n is not None and n not in KNOWN_OFFER_PCTS:
            result["warnings"].append(f"unverified percentage: '{m.group(0)}'")
    for m in _DOLLAR_RE.finditer(plain):
        try:
            v = round(float(m.group(1)), 2)
        except ValueError:
            continue
        if v not in prices and v not in KNOWN_OFFER_DOLLARS:
            result["warnings"].append(f"unverified dollar figure: ${m.group(1)}")

    result["ok"] = not result["problems"]
    return result


def report(res: dict) -> str:
    """One readable block for a re-run nudge, a banner, or a dispatch note."""
    lines = []
    if res.get("problems"):
        lines.append("PROBLEMS (must fix):")
        lines += [f"  - {p}" for p in res["problems"]]
    if res.get("warnings"):
        lines.append("UNVERIFIED NUMBERS (remove or source them):")
        lines += [f"  - {w}" for w in res["warnings"]]
    if res.get("checked"):
        lines.append("Live stock checked: " + " | ".join(res["checked"]))
    if not res.get("verified"):
        lines.append("(The store could not be read, so nothing above is proven either way.)")
    return "\n".join(lines) if lines else "No claims found to check."


def banner(res: dict) -> str:
    return BANNER + "\n" + report(res) + "\n" + "-" * 60 + "\n"
