"""DEREK WRITES IT, VIVIAN DESIGNS IT -- designed emails built in Omnisend's own blocks (2026-09-26).

Barry, 2026-09-26: "Dereks emaisl have no art work, from vivian. its just plaine. i dont like that" /
"I need to really see it as it will go out" / "vivian could use whatever tools they have for design" /
"derek comes up with email posts, products coupons, tips, etc and vivian comes up with style and design" /
(of the first plain build) "really basic, nothing like the reference i gave you" -- his reference is the
modern template look: full-bleed photo heroes with the headline on the picture, colour bands, 3-across
feature rows, alternating photo/text rows, product cards, bold two-tone headlines.

THE SPLIT, IN CODE:
  DEREK owns the WORDS and the substance -- a CONTENT SHEET (parse_sheet): subject, preheader, eyebrow,
    headline, subhead, banner line, section headings + copy, feature points, which products, which
    coupon, the button. It is fact-checked against the live store.
  VIVIAN owns the LOOK -- a DESIGN (the design_email tool): which blocks, in what order, what colours,
    what pictures (her own renders or the real product photos), how the headline, products, points and
    coupon are presented. Her design PLACES Derek's words by number; it cannot add or change one word.
    Product cards are filled from the live store (name, price, photo, link). The legal footer (address +
    unsubscribe) is always added by code and cannot be designed away.

THE BUILD: the design becomes an Omnisend email template in Omnisend's own block format (the format of
his own "Bionova 20% - 7 day promo" template: data/omnisend_template_sample_bionova_promo.json), so he
can open and tweak it in Omnisend's editor too. Pictures go to Omnisend's own hosting. Omnisend renders
it; that HTML is screenshotted by headless Firefox (software rendering, never the GPU) and the full-length
screenshot is what his approval card shows and what Vivian looks at. Approve = a campaign FROM THAT
TEMPLATE (dispatch.py): what he saw is what goes out. Before his click only DRAFT assets exist in
Omnisend (template + images) -- no campaign, nothing can send.

MEASURED AGAINST THE LIVE API (2026-09-26): an image block's id AND source must use the FILE id at the
end of the upload's `url` (the record `id` serves a 35-byte blank GIF); source is /image/newsletter/<id>
(the CDN url is rejected); Omnisend's "preheader" block is the VISIBLE view-in-browser line, so the
inbox preview goes on the campaign instead.

Files per draft: data/email_designs/<approval_id>/ {sheet.json, design.json, img_<name>.png,
preview.html, preview.png}.
"""
from __future__ import annotations

import hashlib
import html as _html
import json
import os
import re
import secrets
import subprocess
import tempfile

import httpx

import memory
import omnisend_client as om

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(_ROOT, "data", "email_designs")
_IMG_CACHE = os.path.join(DIR, "image_cache.json")
FIREFOX = r"C:\Program Files\Mozilla Firefox\firefox.exe"

# B Dubb Grows brand, from Vivian's own palette doc (colour-theory-and-brand-palette.md). The tints are
# that doc's PROPOSED tokens. #FF7900 is an ACCENT ONLY -- it fails contrast as text on white; the code
# only ever puts accent-coloured WORDS on dark backgrounds.
BRAND = {
    "green": "#008903", "body_green": "#47704C", "accent": "#FF7900", "dark": "#1e3d2f",
    "deep_green": "#0a5c0e", "heading": "#16211a", "text": "#1f231f", "muted": "#5c655f",
    "white": "#FFFFFF", "tint": "#eef6ee", "light_tint": "#cfe6cf", "light": "#f7f8f6",
    "peach": "#ffe9d4", "border": "#dde1dc", "page": "#EDEEF0",
}
DARK_BGS = {BRAND["dark"].lower(), BRAND["heading"].lower(), BRAND["green"].lower(), BRAND["deep_green"].lower(),
            BRAND["body_green"].lower()}
FONT = "Poppins, Helvetica Neue, Helvetica, Arial, sans-serif"
WIDTH, PAD = 600, 24
MAX_RENDERS = 3
RENDER_SIZES = {"wide": (1344, 672), "square": (1024, 1024), "tall": (896, 1152)}

# From his own Omnisend template (the account's uploaded logo) + his real social pages.
LOGO = {"id": "6a70efa3db75d5515dd24948", "source": "/image/newsletter/6a70efa3db75d5515dd24948",
        "altText": "B DUBB GROWS LLC", "width": 248, "height": 86}
SOCIAL = [("facebook", "https://facebook.com/BDUBB4ch"),
          ("instagram", "https://instagram.com/b.dubb_growsllc"),
          ("tiktok", "https://tiktok.com/@bdubbgrows")]
# THE FOOTER ADDRESS (Barry, 2026-09-26: "i dont want my address in the bottom of the email" -> "you change it").
# His business mailbox, typed here so no email can fall back to Omnisend's old account field (1919 Monterey Rd).
# The law needs a real postal address in every marketing email; a PMB qualifies. His personal name never goes in.
BUSINESS_NAME = "B DUBB GROWS"
BUSINESS_ADDRESS = "6510-A S Academy Blvd PMB3016, Colorado Springs, CO 80906-8691, United States"
OFFER_FOOTNOTE = "To get both discounts, use the codes separately - they can't be combined on the same order."
OFFERS = {"BIG15": "Bionova only", "BIG10": "everything except Bionova"}


# === DEREK'S CONTENT SHEET =======================================================================

_FIELD = re.compile(r"^(SUBJECT|PREHEADER|EYEBROW|HEADLINE|SUBHEAD|BANNER|HEADING\s*\d+|SECTION\s*\d+|"
                    r"POINT\s*\d+|PRODUCTS|OFFER LINE|OFFER|CTA|PRODUCT BUTTON|FOR VIVIAN)\s*:\s*", re.I | re.M)

SHEET_FORMAT = (
    "FORMAT -- a CONTENT SHEET, exactly these labels, each at the start of a line. Every word in the "
    "email comes from this sheet, so write the REAL substance -- what the product actually does (from "
    "read_product), the real tip a grower can use today, the real offer:\n"
    "SUBJECT: the subject line (under 50 characters works best on phones)\n"
    "PREHEADER: the grey preview line inboxes show after the subject (40-90 characters)\n"
    "EYEBROW: a 1-4 word label above the headline, like COCO GROWERS or NEW IN (optional)\n"
    "HEADLINE: the big line at the top -- short, 3-8 words\n"
    "SUBHEAD: one sentence under it (optional)\n"
    "BANNER: one short line for a colour stripe, e.g. a true shipping fact (optional)\n"
    "HEADING 1: a short heading for section 1 (optional; HEADING n goes with SECTION n)\n"
    "SECTION 1: body copy, simple HTML -- <p>, <strong>, <a href>, <br> only. 2-4 sentences, one idea.\n"
    "SECTION 2: ... (as many as the email needs -- a tip section, a product section, a how-to...)\n"
    "POINT 1: title | one sentence (optional -- 2 or 3 quick points: steps, benefits, feeding facts)\n"
    "POINT 2: title | one sentence\n"
    "PRODUCTS: exact store product names separated by ; (or none) -- read each with read_product first\n"
    "OFFER: BIG15 or BIG10 or none\n"
    "OFFER LINE: the one line that sells the offer (only if OFFER is a code)\n"
    "CTA: the main button words -> the full https link it goes to\n"
    "PRODUCT BUTTON: the words on each product card's button (optional, default: Shop now)\n"
    "FOR VIVIAN: one or two lines -- the job the design has to do (the feel, what must stand out)\n"
    "Nothing before SUBJECT and nothing after FOR VIVIAN. Vivian designs it; you never write layout, "
    "colours or picture directions beyond FOR VIVIAN."
)


def parse_sheet(text: str) -> dict | None:
    text = re.sub(r"^```\w*\s*|\s*```$", "", (text or "").strip(), flags=re.S)
    marks = list(_FIELD.finditer(text))
    if not marks:
        return None
    out: dict = {"sections": {}, "headings": {}, "points": {}}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        key = re.sub(r"\s+", " ", m.group(1).upper())
        val = text[m.end():end].strip()
        num = re.search(r"\d+", key)
        if key.startswith("SECTION"):
            out["sections"][int(num.group(0))] = val
        elif key.startswith("HEADING"):
            out["headings"][int(num.group(0))] = val
        elif key.startswith("POINT"):
            t, _, s = val.partition("|")
            out["points"][int(num.group(0))] = {"title": t.strip(), "text": s.strip()}
        else:
            out[key.lower().replace(" ", "_")] = val
    if not out.get("subject") or not out["sections"]:
        return None
    prods = out.get("products", "")
    out["products"] = [] if prods.strip().lower() in ("", "none", "-") else \
        [p.strip() for p in re.split(r"[;\n]", prods) if p.strip()]
    code = (out.get("offer") or "").strip().upper()
    out["offer"] = code if code in OFFERS else ""
    m = re.match(r"(.+?)\s*(?:->|→|\|)\s*(https?://\S+)", out.get("cta", ""))
    out["cta_text"], out["cta_link"] = (m.group(1).strip(), m.group(2).strip()) if m else ("", "")
    out["product_button"] = (out.get("product_button") or "").strip() or "Shop now"
    return out


def sheet_gaps(sheet: dict, kind: str = "", tool_names: list | None = None) -> list[str]:
    """THE CONTENT BAR (Barry, 2026-09-26: "theres no info about the product or a tip. just basic" /
    "i need high Level every time"). A sheet below this bar goes back to Derek once, with the gaps."""
    gaps = []
    tools = [str(t).split("(")[0] for t in (tool_names or [])]
    head = (sheet.get("headline") or "").split()
    if not head:
        gaps.append("no HEADLINE")
    elif len(head) > 10:
        gaps.append(f"HEADLINE is {len(head)} words -- 3 to 8 lands on a phone")
    if len(sheet.get("subject", "")) > 60:
        gaps.append(f"SUBJECT is {len(sheet['subject'])} characters -- phones cut it near 40-50")
    if not sheet.get("preheader"):
        gaps.append("no PREHEADER -- the inbox then shows a random first line")
    secs = [_plain(v) for v in sheet["sections"].values()]
    if len(secs) < 2:
        gaps.append("only one SECTION -- a real email carries at least the hook and the substance")
    thin = [n for n, v in sheet["sections"].items() if len(re.findall(r"[.!?](\s|$)", _plain(v))) < 2]
    if thin:
        gaps.append(f"SECTION(s) {thin} are a single sentence -- say the real thing: what, why, how")
    if kind == "grower-tip" and len(sheet.get("points") or {}) < 2 and len(secs) < 3:
        gaps.append("a grower tip needs the actual how-to: 2-3 POINTs (steps) or a full how-to section")
    if kind in ("product-feature", "reorder-reminder") and not sheet.get("products"):
        gaps.append(f"a {kind} with no PRODUCTS -- name the real product(s)")
    if sheet.get("products") and tool_names is not None and "read_product" not in tools:
        gaps.append("PRODUCTS listed but read_product was never called -- read each description before writing")
    if not sheet.get("cta_link"):
        gaps.append("CTA needs 'words -> https://link'")
    if sheet.get("offer") and not sheet.get("offer_line"):
        gaps.append("OFFER code with no OFFER LINE")
    if not sheet.get("for_vivian"):
        gaps.append("no FOR VIVIAN brief -- tell her the job the design has to do")
    return gaps


def design_warnings(design: dict, sheet: dict) -> list[str]:
    """Not blockers -- the things that make an email read 'basic'. Handed to Vivian with her screenshot."""
    w = []
    layout = design.get("layout") or []
    kinds = [b.get("block") for b in layout]
    imgs = design.get("images") or {}
    if "hero" not in kinds:
        w.append("no hero -- the first screen is the email; open with one")
    for b in layout:
        if b.get("block") == "hero" and b.get("style", "overlay") == "overlay":
            spec = imgs.get(b.get("image") or "") or {}
            if spec.get("art") == "product":
                w.append("a product photo behind an overlay headline fights the words -- use a scene render "
                         "with open space, or a split hero for the bottle")
            if not b.get("image"):
                w.append("overlay hero with no picture is just a colour block")
    if not imgs and not sheet.get("products"):
        w.append("no pictures at all -- this will read plain")
    bgs = [(b.get("background") or "white") for b in layout if b.get("block") not in ("divider", "spacer")]
    for i in range(len(bgs) - 2):
        if bgs[i] == bgs[i + 1] == bgs[i + 2]:
            w.append(f"three sections in a row on '{bgs[i]}' (blocks {i}-{i + 2}) -- alternate bands for rhythm")
            break
    if kinds.count("cta") > 1:
        w.append("more than one standalone cta block -- one main action")
    if sheet.get("products") and len(sheet["products"]) >= 2 and "products" not in kinds:
        w.append("two or more products shown only one at a time -- a products row lets them compare")
    return w


def _plain(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", _html.unescape(s or ""))).strip()


def sheet_text(s: dict) -> str:
    """The sheet as plain reading text: the card's words and what the fact-check reads."""
    lines = [s.get("subject", ""), ""]
    for k in ("preheader", "eyebrow", "headline", "subhead", "banner"):
        if s.get(k):
            lines.append(f"{k.upper()}: {s[k]}")
    for n in sorted(s["sections"]):
        if s["headings"].get(n):
            lines += ["", s["headings"][n].upper()]
        else:
            lines.append("")
        lines.append(_plain(s["sections"][n]))
    for n in sorted(s.get("headings", {})):
        if n not in s["sections"]:                       # a heading that titles a products row, etc.
            lines += ["", s["headings"][n].upper()]
    for n in sorted(s.get("points", {})):
        p = s["points"][n]
        lines.append(f"- {p['title']}: {p['text']}")
    if s.get("products"):
        lines += ["", "PRODUCTS: " + "; ".join(s["products"])]
    if s.get("offer"):
        lines += ["", f"OFFER: {s['offer']} -- {s.get('offer_line', '')}", OFFER_FOOTNOTE]
    if s.get("cta_text"):
        lines += ["", f"BUTTON: {s['cta_text']} -> {s['cta_link']}"]
    return "\n".join(lines).strip()


# === THE STORE (product cards are the store's data, never typed) ==================================

def product_card(name: str) -> dict:
    import store
    hits = store._search_products(name)
    if not hits:
        raise ValueError(f"no store product matches '{name}'")
    p = hits[0]
    real = _html.unescape(p.get("name", ""))
    if p.get("stock_status") != "instock":
        raise ValueError(f"'{real}' is {p.get('stock_status')} -- an email never features it")
    price, regular, sale = p.get("price") or "", p.get("regular_price") or "", p.get("sale_price") or ""
    imgs = p.get("images") or []
    # A VARIABLE product's "price" is its CHEAPEST variation (Coco Forte A + B: $14.95 is one 1 L bottle
    # of Part A; the A + B pair starts at $23.95). Showing it bare would be a false price -> "From".
    variable = p.get("type") == "variable"
    return {"name": real, "price": (f"From ${price}" if variable else f"${price}"),
            "was": (f"${regular}" if sale and sale != regular and not variable else ""),
            "link": p.get("permalink", ""), "photo": imgs[0].get("src", "") if imgs else ""}


# === OMNISEND ======================================================================================

def _hdr(json_body: bool = True) -> dict:
    h = om.headers()
    if not json_body:
        h.pop("Content-Type", None)
    return h


def _req(method: str, path: str, **kw) -> dict:
    if not om.is_configured():
        raise om.OmnisendError("No OMNISEND_API_KEY set -- nothing was built.")
    r = httpx.request(method, f"{om.API_ROOT}{path}", timeout=60, **kw)
    if r.status_code >= 400:
        raise om.OmnisendError(f"Omnisend {r.status_code}: {r.text[:500]}")
    return r.json() if r.content else {}


def _cache() -> dict:
    try:
        return json.load(open(_IMG_CACHE, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def upload_image(src: str, name: str, max_w: int = 1200, darken: int = 0, square: bool = False) -> dict:
    """A local file or a store photo URL -> Omnisend-hosted image {id, url, width, height}.
    JPEG (WebP is not safe in every inbox), max 1200 px wide. `darken` (0-70 %) lays a dark wash over it
    so white headline text reads on a photo; `square` pads a product shot onto a white square so cards
    line up. Cached by (source, darken, square)."""
    key = f"{src}|d{int(darken)}|s{int(square)}"
    c = _cache()
    if key in c:
        return c[key]
    from io import BytesIO
    from PIL import Image
    raw = open(src, "rb").read() if os.path.exists(src) else httpx.get(
        src, timeout=60, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}).content
    im = Image.open(BytesIO(raw))
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    im = im.convert("RGB")
    if square and im.width != im.height:
        s = max(im.size)
        sq = Image.new("RGB", (s, s), (255, 255, 255))
        sq.paste(im, ((s - im.width) // 2, (s - im.height) // 2))
        im = sq
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    if darken:
        im = Image.blend(im, Image.new("RGB", im.size, (10, 20, 14)), max(0, min(70, int(darken))) / 100)
    buf = BytesIO()
    im.save(buf, "JPEG", quality=86, optimize=True, progressive=True)
    fname = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] + ".jpg"
    d = _req("POST", "/images/upload", headers=_hdr(False),
             files={"file": (fname, buf.getvalue(), "image/jpeg")}, data={"name": fname})
    url = d.get("url") or ""
    out = {"id": url.rsplit("/", 1)[-1] if url else d.get("id"), "record_id": d.get("id"), "url": url,
           "width": d.get("width") or im.width, "height": d.get("height") or im.height}
    c[key] = out
    os.makedirs(DIR, exist_ok=True)
    json.dump(c, open(_IMG_CACHE, "w", encoding="utf-8"), indent=1)
    return out


# === THE TEMPLATE (Omnisend's block format) =========================================================

def _id() -> str:
    return secrets.token_hex(12)                         # 24 hex chars, as Omnisend requires


def _color(v, default):
    v = (v or "").strip() if isinstance(v, str) else ""
    if v in BRAND:
        return BRAND[v]
    return v if re.fullmatch(r"#[0-9a-fA-F]{6}", v) else default


def _is_dark(hexc: str | None) -> bool:
    if not hexc:
        return False
    if hexc.lower() in DARK_BGS:
        return True
    h = hexc.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) < 110


# ORANGE AS TEXT ONLY WHERE IT READS (2026-09-26, measured): #FF7900 on #1e3d2f is 4.53:1 and on
# #16211a higher -- fine. On the brand greens it is 1.74:1 (#008903) / 2.16:1 (#47704C): unreadable.
# A darkened overlay photo counts as near-black. Everywhere else the "accent" text falls back.
_ORANGE_OK = {BRAND["dark"].lower(), BRAND["heading"].lower()}


def _orange_ok(bg, overlay_photo: bool = False) -> bool:
    return overlay_photo or (bool(bg) and bg.lower() in _ORANGE_OK)


def _text(html: str, preset: str, align: str = "left", **style) -> dict:
    sp = {"padding": style.pop("padding", "8px 12px"), "alignment": align}
    sp.update({k: v for k, v in style.items() if v})
    if align != "left":
        html = re.sub(r"<p(?![^>]*text-align)", f'<p style="text-align: {align};"', html)
    return {"id": _id(), "type": "text", "text": html, "styleProperties": sp, "stylePresetID": preset}


def _p(s: str, extra: str = "") -> str:
    s = (s or "").strip()
    if s.lower().startswith("<p"):
        return s
    return f'<p style="margin: 0px;{extra}">{s}</p>'


def _button(text: str, link: str, preset: str = "primary_button", align: str = "center",
            full: bool = False) -> dict:
    return {"id": _id(), "type": "button",
            "button": {"text": text, "link": link, "isFullWidth": full, "translationKey": ""},
            "styleProperties": {"padding": "12px", "alignment": align}, "stylePresetID": preset}


def _image(img: dict, alt: str, link: str = "", width: int = WIDTH - 2 * PAD, pad: str = "0px",
           radius: str = "") -> dict:
    h = round(img["height"] * width / max(1, img["width"]))
    sp = {"padding": pad, "alignment": "center"}
    if radius:
        sp["borderRadius"] = radius
    return {"id": _id(), "type": "image",
            "image": {"id": img["id"], "source": f"/image/newsletter/{img['id']}", "altText": alt,
                      "link": link, "resizeWidth": width, "resizeHeight": h,
                      "width": img["width"], "height": img["height"]},
            "styleProperties": sp}


PADS = {"tight": (8, 8), "normal": (16, 16), "roomy": (32, 32), "hero": (72, 72)}


def _section(cols: list[list[dict]], bg: str | None = None, pad=(PAD, PAD, 16, 16), widths=None,
             col_styles: list[dict] | None = None, bg_image: dict | None = None) -> dict:
    n = len(cols)
    inner = WIDTH - pad[0] - pad[1]
    widths = widths or [inner // n] * n
    sp = {"paddingLeft": f"{pad[0]}px", "paddingRight": f"{pad[1]}px",
          "paddingTop": f"{pad[2]}px", "paddingBottom": f"{pad[3]}px"}
    if bg:
        sp["backgroundColor"] = bg
    if bg_image:
        sp.update({"backgroundImageID": bg_image["id"], "backgroundSize": "cover",
                   "backgroundPosition": "center center", "backgroundRepeat": "no-repeat"})
    columns = []
    for i, (w, b) in enumerate(zip(widths, cols)):
        col = {"id": _id(), "width": f"{w}px", "blocks": b}
        if col_styles and i < len(col_styles) and col_styles[i]:
            col["styleProperties"] = col_styles[i]
        columns.append(col)
    sec = {"id": _id(), "styleProperties": sp, "rows": [{"id": _id(), "columns": columns}]}
    if bg_image:   # measured 09-26: without backgroundType "image" Omnisend silently drops the picture
        sec["settings"] = {"backgroundType": "image"}
    return sec


def general_settings(style: dict) -> dict:
    heading = _color(style.get("heading_color"), BRAND["heading"])
    text = _color(style.get("text_color"), BRAND["text"])
    btn = _color(style.get("button_color"), BRAND["green"])
    btn_txt = _color(style.get("button_text_color"), BRAND["white"])
    radius = str(style.get("button_radius", "6px"))
    hsize = max(24, min(48, int(style.get("heading_size", 36) or 36)))
    up = {"textTransform": "uppercase", "letterSpacing": "1px"} if style.get("uppercase_headings") else {}
    base = {"fontFamily": FONT, "lineHeight": "120%", "fontWeight": "bold"}
    btn_base = {"borderRadius": radius, "fontFamily": FONT, "fontWeight": "bold",
                "paddingLeft": "30px", "paddingRight": "30px", "paddingTop": "15px", "paddingBottom": "15px"}
    return {
        "content": {"backgroundColor": _color(style.get("content_color"), BRAND["white"]),
                    "width": f"{WIDTH}px", "fontFamily": FONT, "fontSize": "16px", "color": text},
        "logo": dict(LOGO),
        "body": {"backgroundColor": _color(style.get("page_color"), BRAND["page"])},
        "textPresets": [
            {"id": "heading_large", "name": "Heading large", "styles": dict(base, fontSize=f"{hsize}px", color=heading, **up)},
            {"id": "heading_medium", "name": "Heading medium", "styles": dict(base, fontSize=f"{round(hsize * .72)}px", color=heading, **up)},
            {"id": "heading_small", "name": "Heading small", "styles": dict(base, fontSize=f"{round(hsize * .55)}px", color=heading)},
            {"id": "paragraph", "name": "Paragraph",
             "styles": {"fontFamily": FONT, "fontSize": "16px", "color": text, "lineHeight": "160%"}},
            {"id": "footnote", "name": "Footnote",
             "styles": {"fontFamily": FONT, "fontSize": "12px", "color": BRAND["muted"], "lineHeight": "150%"}},
        ],
        "buttonPresets": [
            {"id": "primary_button", "name": "Primary",
             "styles": dict(btn_base, backgroundColor=btn, color=btn_txt, fontSize="16px")},
            {"id": "secondary_button", "name": "Outline",
             "styles": dict(btn_base, backgroundColor="#FFFFFF", border=f"2px solid {btn}", color=btn,
                            fontSize="15px", paddingTop="12px", paddingBottom="12px")},
            {"id": "tertiary_button", "name": "Accent",
             "styles": dict(btn_base, backgroundColor=BRAND["accent"], color=BRAND["heading"], fontSize="16px")},
        ],
    }


BLOCK_KINDS = ("hero", "banner", "text", "features", "image", "image_text", "products", "offer", "cta",
               "divider", "spacer")
BUTTONS = {"primary": "primary_button", "outline": "secondary_button", "secondary": "secondary_button",
           "accent": "tertiary_button"}


def _renders(design: dict) -> dict:
    return {k: v for k, v in (design.get("images") or {}).items()
            if isinstance(v, dict) and (v.get("art") or "").lower() == "render"}


def check_design(design: dict, sheet: dict) -> list[str]:
    """Problems that stop a build. Derek's content must all be placed, exactly once each."""
    probs = []
    layout = design.get("layout") or []
    if not isinstance(layout, list) or not layout:
        return ["design.layout is empty -- list the blocks top to bottom"]
    imgs = design.get("images") or {}
    for k, v in imgs.items():
        art = (v or {}).get("art")
        if art == "render" and not (v.get("scene") or "").strip():
            probs.append(f"images.{k}: a render needs a scene")
        if art == "product" and v.get("product") not in sheet.get("products", []):
            probs.append(f"images.{k}: '{v.get('product')}' is not one of Derek's PRODUCTS")
        if art not in ("render", "product"):
            probs.append(f"images.{k}: art must be render or product")
    if len(_renders(design)) > MAX_RENDERS:
        probs.append(f"{len(_renders(design))} renders -- at most {MAX_RENDERS} per email (each is ~6 min on the card)")
    used, kinds = [], []
    for i, b in enumerate(layout):
        kind = (b or {}).get("block")
        kinds.append(kind)
        if kind not in BLOCK_KINDS:
            probs.append(f"layout[{i}]: unknown block '{kind}' (use one of {', '.join(BLOCK_KINDS)})")
            continue
        if kind in ("text", "image_text"):
            n = b.get("section")
            if n not in sheet["sections"]:
                probs.append(f"layout[{i}]: section {n} is not in Derek's sheet (he wrote {sorted(sheet['sections'])})")
            used.append(n)
        im = b.get("image")
        if im and im != "none" and im not in imgs:
            probs.append(f"layout[{i}]: image '{im}' is not defined in design.images")
        if kind == "image_text" and not im and not b.get("product"):
            probs.append(f"layout[{i}]: image_text needs an image (from design.images) or one of Derek's products")
        if b.get("product") and b["product"] not in sheet.get("products", []):
            probs.append(f"layout[{i}]: '{b['product']}' is not one of Derek's PRODUCTS -- the products are his call")
    missing = [n for n in sheet["sections"] if n not in used]
    if missing:
        probs.append(f"Derek's section(s) {missing} are not placed -- every section he wrote goes in, once")
    dup = sorted({n for n in used if used.count(n) > 1})
    if dup:
        probs.append(f"section(s) {dup} placed more than once")
    if sheet.get("points") and "features" not in kinds:
        probs.append("Derek wrote POINTs -- place them with a features block")
    if sheet.get("banner") and "banner" not in kinds:
        probs.append("Derek wrote a BANNER line -- place it with a banner block")
    if sheet.get("products") and "products" not in kinds and not any(
            b.get("block") == "image_text" and b.get("product") for b in layout):
        probs.append("Derek listed PRODUCTS but the layout shows none -- add a products or image_text block")
    if sheet.get("offer") and "offer" not in kinds:
        probs.append(f"Derek's offer {sheet['offer']} is not placed -- add an offer block")
    if sheet.get("cta_text") and "cta" not in kinds and "hero" not in kinds:
        probs.append("Derek's main button is not placed -- add a cta block (or a hero, which carries it)")
    if "hero" in kinds and kinds.index("hero") != 0:
        probs.append("the hero goes first")
    return probs


def _headline_html(sheet: dict, accent_words: int, dark: bool) -> str:
    words = _html.escape(sheet.get("headline", "")).split()
    k = max(0, min(int(accent_words or 0), len(words) - 1)) if dark else 0   # accent only on dark
    if k:
        words = words[:-k] + [f'<span style="color: {BRAND["accent"]};">' + " ".join(words[-k:]) + "</span>"]
    return _p("<strong>" + " ".join(words) + "</strong>")


def build_template(name: str, design: dict, sheet: dict, images: dict) -> dict:
    """images: {name: uploaded image or None (render still pending)}."""
    style = design.get("style") or {}
    S = []
    cards = {}
    for pname in sheet.get("products", []):
        c = product_card(pname)
        c["img"] = upload_image(c["photo"], c["name"], max_w=600, square=True) if c["photo"] else None
        cards[pname] = c

    # header
    head_bg = _color(style.get("header_color"), BRAND["white"])
    S.append(_section([[{"id": _id(), "type": "logo",
                         "logo": {"link": "https://bdubbgrowsllc.com", "resizeWidth": int(style.get("logo_width", 120))},
                         "styleProperties": {"padding": "6px", "alignment": style.get("logo_align", "center")}}]],
                      bg=head_bg, pad=(PAD, PAD, 14, 10)))

    for b in design["layout"]:
        kind = b.get("block")
        bg = _color(b.get("background"), None) if b.get("background") else None
        align = b.get("align", "left")
        pt, pb = PADS.get(b.get("pad", "normal"), PADS["normal"])
        on_dark = _is_dark(bg)
        txt_color = "#FFFFFF" if on_dark else None
        btn = BUTTONS.get(b.get("button_style", "primary"), "primary_button")

        if kind == "hero":
            hstyle = b.get("style", "overlay")
            hb = _color(b.get("background"), BRAND["dark"])
            img_name = b.get("image")
            img = images.get(img_name) if img_name else None
            dark = _is_dark(hb) or (hstyle == "overlay" and img is not None)
            col = "#FFFFFF" if dark else None
            halign = b.get("align", "center")
            words = []
            if sheet.get("eyebrow"):
                words.append(_text(_p(f"<strong>{_html.escape(sheet['eyebrow'].upper())}</strong>",
                                      " letter-spacing: 3px;"), "footnote", halign,
                                   color=(BRAND["accent"] if _orange_ok(hb, hstyle == "overlay" and img is not None) else (BRAND["light_tint"] if dark else BRAND["green"])), padding="0px 12px"))
            words.append(_text(_headline_html(sheet, b.get("accent_words", 0), _orange_ok(hb, hstyle == "overlay" and img is not None)), "heading_large", halign,
                               color=col, padding="2px 12px"))
            if sheet.get("subhead"):
                words.append(_text(_p(_html.escape(sheet["subhead"])), "paragraph", halign, color=col,
                                   fontSize="17px", padding="2px 12px 8px 12px"))
            if sheet.get("cta_text") and b.get("button", True):
                words.append(_button(sheet["cta_text"], sheet["cta_link"],
                                     BUTTONS.get(b.get("button_style", "accent" if dark else "primary")), halign))
            if hstyle == "overlay":
                # the picture IS the background, the headline sits on it (his reference's look)
                S.append(_section([words], bg=hb, pad=(PAD, PAD) + PADS.get(b.get("pad", "hero"), PADS["hero"]),
                                  bg_image=img))
            elif hstyle == "split" and img:
                side = b.get("side", "left")
                pic = [_image(img, sheet.get("headline", ""), sheet.get("cta_link", ""), width=276, pad="0px")]
                cols = [pic, words] if side == "left" else [words, pic]
                S.append(_section(cols, bg=hb, pad=(0, 0, 0, 0), widths=[300, 300],
                                  col_styles=[{"verticalAlign": "middle"}] * 2))
            else:   # stacked: full-bleed picture, then the words on a colour band
                if img:
                    S.append(_section([[_image(img, sheet.get("headline", ""), sheet.get("cta_link", ""),
                                               width=WIDTH)]], bg=hb, pad=(0, 0, 0, 0)))
                S.append(_section([words], bg=hb, pad=(PAD, PAD, 28, 32)))

        elif kind == "banner" and sheet.get("banner"):
            bb = _color(b.get("background"), BRAND["accent"])
            col = "#FFFFFF" if _is_dark(bb) else BRAND["heading"]
            S.append(_section([[_text(_p(f"<strong>{_html.escape(sheet['banner'].upper())}</strong>",
                                         " letter-spacing: 2px;"), "footnote", "center", color=col,
                                      fontSize="13px", padding="4px 12px")]], bg=bb, pad=(PAD, PAD, 10, 10)))

        elif kind == "text":
            n = b["section"]
            blk = []
            if sheet["headings"].get(n):
                blk.append(_text(_p(f"<strong>{_html.escape(sheet['headings'][n])}</strong>"), "heading_medium",
                                 align, color=txt_color, padding="0px 12px"))
            blk.append(_text(sheet["sections"][n], "paragraph", align, color=txt_color, linkColor=
                             BRAND["light_tint"] if on_dark else BRAND["green"]))
            S.append(_section([blk], bg=bg, pad=(PAD + 8, PAD + 8, pt, pb)))

        elif kind == "features" and sheet.get("points"):
            pts = [sheet["points"][k] for k in sorted(sheet["points"])][:3]
            marker = b.get("marker", "number")
            mark_col = BRAND["accent"] if _orange_ok(bg) else (BRAND["light_tint"] if on_dark else BRAND["green"])
            cols = []
            for i, p in enumerate(pts, 1):
                col = []
                if marker == "number":
                    col.append(_text(_p(f"<strong>{i:02d}</strong>"), "heading_medium", "center",
                                     color=mark_col, padding="4px 8px"))
                elif marker == "bar":
                    col.append(_text(f'<p style="margin: 0px auto; width: 40px; border-top: 4px solid {mark_col};">&nbsp;</p>',
                                     "footnote", "center", padding="4px 8px"))
                col.append(_text(_p(f"<strong>{_html.escape(p['title'])}</strong>"), "heading_small", "center",
                                 color=txt_color, padding="0px 8px"))
                col.append(_text(_p(_html.escape(p["text"])), "paragraph", "center", color=txt_color,
                                 fontSize="14px", lineHeight="150%", padding="2px 8px"))
                cols.append(col)
            S.append(_section(cols, bg=bg, pad=(PAD, PAD, pt + 8, pb + 8)))

        elif kind == "image":
            img = images.get(b.get("image"))
            if img:
                full = b.get("full_bleed", True)
                S.append(_section([[_image(img, sheet.get("headline", ""), sheet.get("cta_link", ""),
                                           width=WIDTH if full else WIDTH - 2 * PAD,
                                           radius=b.get("radius", "") if not full else "")]],
                                  bg=bg, pad=(0, 0, 0, 0) if full else (PAD, PAD, pt, pb)))

        elif kind == "image_text":
            n = b["section"]
            c = cards.get(b.get("product")) if b.get("product") else None
            img = images.get(b.get("image")) if b.get("image") else (c["img"] if c else None)
            txt = []
            if sheet["headings"].get(n):
                txt.append(_text(_p(f"<strong>{_html.escape(sheet['headings'][n])}</strong>"), "heading_small",
                                 "left", color=txt_color, padding="4px 12px"))
            txt.append(_text(sheet["sections"][n], "paragraph", "left", color=txt_color, fontSize="15px"))
            if c:
                txt.append(_text(_p(f"<strong>{c['price']}</strong>" + (
                    f' <span style="text-decoration: line-through; font-weight: normal;">{c['was']}</span>'
                    if c["was"] else "")), "heading_small", "left",
                    color=BRAND["accent"] if _orange_ok(bg) else ("#FFFFFF" if on_dark else _color(style.get("price_color"), BRAND["green"])),
                    padding="4px 12px"))
                txt.append(_button(sheet["product_button"], c["link"],
                                   BUTTONS.get(b.get("button_style", "outline")), "left"))
            pic = [_image(img, c["name"] if c else sheet.get("headline", ""), c["link"] if c else "",
                          width=264, pad="0px", radius=b.get("radius", "8px"))] if img else []
            if pic:
                cols = [pic, txt] if b.get("side", "left") == "left" else [txt, pic]
                S.append(_section(cols, bg=bg, pad=(PAD, PAD, pt + 4, pb + 4),
                                  col_styles=[{"verticalAlign": "middle"}] * 2))
            else:
                S.append(_section([txt], bg=bg, pad=(PAD + 8, PAD + 8, pt, pb)))

        elif kind == "products":
            names = [n for n in sheet.get("products", []) if n in cards]
            per = max(1, min(int(b.get("columns", 2) or 2), 3))
            hn = b.get("heading")
            if hn and sheet["headings"].get(hn):
                S.append(_section([[_text(_p(f"<strong>{_html.escape(sheet['headings'][hn])}</strong>"),
                                          "heading_medium", "center", color=txt_color)]], bg=bg, pad=(PAD, PAD, pt + 8, 0)))
            card_bg = _color(b.get("card_color"), BRAND["white"])
            for i in range(0, len(names), per):
                row, styles = [], []
                for n in names[i:i + per]:
                    c = cards[n]
                    colw = (WIDTH - 2 * PAD) // per
                    col = []
                    if c.get("img"):
                        col.append(_image(c["img"], c["name"], c["link"], width=colw - 40, pad="12px 12px 4px 12px",
                                          radius="6px"))
                    col.append(_text(_p(f"<strong>{_html.escape(c['name'])}</strong>"), "paragraph", "center",
                                     fontSize="14px", color=BRAND["heading"], padding="4px 10px"))
                    col.append(_text(_p(f"<strong>{c['price']}</strong>" + (
                        f' <span style="text-decoration: line-through; font-weight: normal; color: #5c655f;">{c['was']}</span>'
                        if c["was"] else "")), "heading_small", "center",
                        color=_color(style.get("price_color"), BRAND["green"]), padding="2px 10px"))
                    col.append(_button(sheet["product_button"], c["link"], btn, "center"))
                    row.append(col)
                    styles.append({"backgroundColor": card_bg, "padding": "6px"})
                S.append(_section(row, bg=bg, pad=(PAD, PAD, pt if i == 0 else 4, pb), col_styles=styles))

        elif kind == "offer" and sheet.get("offer"):
            ob = _color(b.get("background"), BRAND["dark"])
            dark = _is_dark(ob)
            words = [
                _text(_p("<strong>USE CODE</strong>", " letter-spacing: 3px;"), "footnote", "center",
                      color=BRAND["light_tint"] if dark else BRAND["muted"], padding="2px 12px"),
                _text(_p(f"<strong>{sheet['offer']}</strong>", " letter-spacing: 4px;"), "heading_large", "center",
                      color=BRAND["accent"] if _orange_ok(ob) else ("#FFFFFF" if dark else BRAND["green"]), padding="2px 12px"),
            ]
            if sheet.get("offer_line"):
                words.append(_text(_p(_html.escape(sheet["offer_line"])), "paragraph", "center",
                                   color="#FFFFFF" if dark else None, padding="4px 12px"))
            if b.get("button") and sheet.get("cta_text"):
                words.append(_button(sheet["cta_text"], sheet["cta_link"],
                                     BUTTONS.get(b.get("button_style", "accent" if dark else "primary")), "center"))
            words.append(_text(_p(OFFER_FOOTNOTE), "footnote", "center", color=BRAND["border"] if dark else None,
                               padding="6px 12px"))
            S.append(_section([words], bg=ob, pad=(PAD, PAD) + PADS.get(b.get("pad", "roomy"), PADS["roomy"])))

        elif kind == "cta" and sheet.get("cta_text"):
            S.append(_section([[_button(sheet["cta_text"], sheet["cta_link"], btn, "center",
                                        bool(b.get("full_width")))]], bg=bg, pad=(PAD, PAD, pt, pb + 8)))
        elif kind == "divider":
            S.append(_section([[_text(f'<p style="margin: 0px; border-top: 1px solid {BRAND["border"]};">&nbsp;</p>',
                                      "footnote")]], bg=bg, pad=(PAD, PAD, 0, 0)))
        elif kind == "spacer":
            S.append(_section([[_text('<p style="margin: 0px;">&nbsp;</p>', "footnote")]], bg=bg, pad=(PAD, PAD, 0, 0)))

    # THE FOOTER -- always, never designable away: his real social pages + the legal lines Omnisend fills.
    foot_bg = _color(style.get("footer_color"), BRAND["dark"])
    fcol = "#FFFFFF" if _is_dark(foot_bg) else BRAND["muted"]
    S.append(_section([[
        {"id": _id(), "type": "social",
         "social": {"icons": [{"type": t, "link": l, "source": f"dynamicImage/social/{t}/48/24/default"}
                              for t, l in SOCIAL], "size": "24px", "shape": "circle"},
         "styleProperties": {"padding": "12px", "alignment": "center"}},
        _text(f'<p style="margin: 0px;">© {BUSINESS_NAME} · {BUSINESS_ADDRESS}</p>'
              '<p style="margin: 6px 0px 0px 0px;">You are getting this because you '
              'subscribed on our site or made a purchase.</p><p style="margin: 6px 0px 0px 0px;">'
              '<a href="[[preference_link]]" target="_blank">Update preferences</a> · '
              '<a href="[[unsubscribe_link]]" target="_blank">Unsubscribe</a></p>',
              "footnote", "center", color=fcol, linkColor=BRAND["light_tint"] if _is_dark(foot_bg) else BRAND["green"]),
    ]], bg=foot_bg, pad=(PAD, PAD, 24, 28)))
    return {"name": name[:255], "generalSettings": general_settings(style), "sections": S}


# === RENDER + SCREENSHOT ===========================================================================

def render_html(template_id: str) -> str:
    d = _req("POST", f"/email-templates/{template_id}/render", headers=_hdr(), json={})
    if isinstance(d, dict):
        vals = [v for v in d.values() if isinstance(v, str)]
        return max(vals, key=len) if vals else ""
    return str(d)


def screenshot(html: str, out_png: str) -> str:
    """Headless Firefox (software rendering, no GPU) -> full-length PNG, page margins cropped."""
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    src = out_png[:-4] + ".html"
    open(src, "w", encoding="utf-8").write(html)
    prof = tempfile.mkdtemp(prefix="ffshot-")
    try:
        subprocess.run([FIREFOX, "--headless", "--no-remote", "--profile", prof, "--window-size=680,7000",
                        "--screenshot", out_png, "file:///" + src.replace("\\", "/")],
                       capture_output=True, timeout=120, creationflags=0x08000000)
    finally:
        import shutil
        shutil.rmtree(prof, ignore_errors=True)
    try:
        from PIL import Image, ImageChops
        im = Image.open(out_png).convert("RGB")
        bg = Image.new("RGB", im.size, im.getpixel((2, im.height - 2)))
        box = ImageChops.difference(im, bg).getbbox()
        if box:   # Omnisend's body is a 100%-height table: the email sits CENTRED in the window
            im.crop((0, max(0, box[1] - 24), im.width, min(im.height, box[3] + 24))).save(out_png)
    except Exception:  # noqa: BLE001 -- an uncropped screenshot is still the truth
        pass
    return out_png


# === LINKS (Barry, 2026-09-26: "and make sure links work") =========================================
# Every link in Omnisend's render is opened for real. Omnisend's own placeholders ([[...]], {...}) are
# filled at send time and skipped. Facebook/Instagram/TikTok wall off bots, so a non-200 from them is
# "not checkable", never "broken" -- they are his real pages from his own template.
_WALLED = ("facebook.com", "instagram.com", "tiktok.com")


def check_links(html: str) -> dict:
    urls = []
    for u in re.findall(r'href="([^"]+)"', html or ""):
        u = _html.unescape(u).strip()
        if not u.startswith("http") or "[[" in u or "{" in u or u in urls:
            continue
        urls.append(u)
    ok, broken, walled = [], [], []
    with httpx.Client(timeout=20, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/131.0"}) as cx:
        for u in urls:
            try:
                r = cx.get(u)
                code = r.status_code
            except httpx.HTTPError as e:
                code = type(e).__name__
            if isinstance(code, int) and code < 400:
                ok.append(u)
            elif any(w in u for w in _WALLED):
                walled.append(u)
            else:
                broken.append(f"{u} -> {code}")
    return {"checked": len(urls), "ok": len(ok), "broken": broken, "not_checkable": walled}


# === ONE DRAFT, END TO END ==========================================================================

def draft_dir(aid) -> str:
    return os.path.join(DIR, str(aid))


def load(aid) -> tuple[dict, dict | None]:
    d = draft_dir(aid)
    sheet = json.load(open(os.path.join(d, "sheet.json"), encoding="utf-8"))
    for k in ("sections", "headings", "points"):
        sheet[k] = {int(n): v for n, v in (sheet.get(k) or {}).items()}
    dp = os.path.join(d, "design.json")
    return sheet, (json.load(open(dp, encoding="utf-8")) if os.path.exists(dp) else None)


def save_sheet(aid, sheet: dict) -> None:
    os.makedirs(draft_dir(aid), exist_ok=True)
    json.dump(sheet, open(os.path.join(draft_dir(aid), "sheet.json"), "w", encoding="utf-8"), indent=1)


def _scene_file(aid, name: str, scene: str) -> str:
    h = hashlib.sha1(scene.encode("utf-8")).hexdigest()[:10]
    return os.path.join(draft_dir(aid), f"img_{re.sub(r'[^a-z0-9]+', '_', name.lower())}_{h}.png")


def _hero_darken(design: dict, name: str) -> int:
    for b in design.get("layout") or []:
        if b.get("block") == "hero" and b.get("image") == name and b.get("style", "overlay") == "overlay":
            return int(b.get("darken", 35))
    return 0


def resolve_images(aid, design: dict, sheet: dict) -> tuple[dict, list[str]]:
    out, pending = {}, []
    for name, spec in (design.get("images") or {}).items():
        art = (spec.get("art") or "").lower()
        dk = _hero_darken(design, name)
        if art == "product":
            c = product_card(spec["product"])
            out[name] = upload_image(c["photo"], c["name"], darken=dk) if c["photo"] else None
        elif art == "render":
            f = _scene_file(aid, name, spec["scene"])
            if os.path.exists(f):
                out[name] = upload_image(f, f"email-{aid}-{name}", darken=dk)
            else:
                out[name] = None
                pending.append(name)
    return out, pending


def publish(aid, design: dict, template_id: str | None = None) -> dict:
    """Vivian's design for draft #aid -> Omnisend draft template -> Omnisend's render -> screenshot.
    Returns {ok, problems | template_id, preview_png, pending_renders}. Never sends anything."""
    sheet, _ = load(aid)
    probs = check_design(design, sheet)
    if probs:
        return {"ok": False, "problems": probs}
    d = draft_dir(aid)
    json.dump(design, open(os.path.join(d, "design.json"), "w", encoding="utf-8"), indent=1)
    try:
        images, pending = resolve_images(aid, design, sheet)
        tpl = build_template(f"Email draft #{aid} -- {sheet['subject'][:60]}", design, sheet, images)
    except ValueError as e:
        return {"ok": False, "problems": [str(e)]}
    tid = template_id
    if tid is None and str(aid).isdigit():
        with memory.get_db() as conn:
            row = conn.execute("SELECT omnisend_template_id FROM approvals WHERE id=?", (int(aid),)).fetchone()
        tid = (row["omnisend_template_id"] if row else "") or ""
    if tid:
        _req("PUT", f"/email-templates/{tid}", headers=_hdr(), json=tpl)
    else:
        tid = _req("POST", "/email-templates", headers=_hdr(), json=tpl).get("id", "")
    html = render_html(tid)
    png = screenshot(html, os.path.join(d, "preview.png"))
    links = check_links(html)
    json.dump(links, open(os.path.join(d, "links.json"), "w", encoding="utf-8"), indent=1)
    # the prices this build SHOWS -- compared with the live store again at send (price_changes)
    json.dump({n: product_card(n)["price"] for n in sheet.get("products", [])},
              open(os.path.join(d, "prices.json"), "w", encoding="utf-8"), indent=1)
    if str(aid).isdigit():
        with memory.get_db() as conn:
            conn.execute("UPDATE approvals SET omnisend_template_id=?, file_path=? WHERE id=?", (tid, png, int(aid)))
    return {"ok": True, "template_id": tid, "preview_png": png, "pending_renders": pending, "links": links,
            "warnings": design_warnings(design, sheet)}


async def render_images(aid, template_id: str | None = None) -> dict:
    """Every render the design asks for that is not on disk yet -> Qwen-Image (the office's
    business-still engine), one at a time -> rebuild the email with them."""
    import asyncio
    import shutil
    import comfy_image
    sheet, design = load(aid)
    done = []
    for name, spec in _renders(design or {}).items():
        f = _scene_file(aid, name, spec["scene"])
        if os.path.exists(f):
            continue
        if comfy_image.render_in_progress():
            return {"ok": False, "why": "the card is busy with another render", "done": done}
        w, h = RENDER_SIZES.get(spec.get("shape", "wide"), RENDER_SIZES["wide"])
        # BONSAI OUT FIRST (office rule; missing here hung the backend 2026-09-26 17:54 --
        # Bonsai + Laya training + the Qwen model squeezed RAM until the watchdog killed it).
        import llm_router
        await llm_router.unload_all_models()
        import activity
        _tok = activity.begin("Vivian", f"rendering '{name}' for email #{aid} (GPU)", "render")
        try:
            res = await comfy_image.generate_image(prompt=spec["scene"], width=w, height=h)
        finally:
            activity.end(_tok)
        path = (res or {}).get("file_path") or (res or {}).get("path") or ""
        if not path:
            return {"ok": False, "why": f"render '{name}' returned no file", "done": done}
        shutil.copy2(path, f)
        done.append(name)
    r = await asyncio.to_thread(publish, aid, design, template_id)
    return dict(r, rendered=done)


def price_changes(aid) -> list[str]:
    """Barry, 2026-09-26: "yes recheck prices at send too." Every product in the built email against
    the live store NOW. Returns what changed; raises ValueError if a product went out of stock."""
    p = os.path.join(draft_dir(aid), "prices.json")
    if not os.path.exists(p):
        return []
    shown = json.load(open(p, encoding="utf-8"))
    out = []
    for name, was in shown.items():
        now = product_card(name)["price"]          # ValueError if it is no longer in stock
        if now != was:
            out.append(f"{name}: {was} on the card, {now} in the store now")
    return out


