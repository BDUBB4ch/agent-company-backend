"""HER GRIMOIRE (2026-10-19, Barry: "i would love her to have her own grimoir" / "Yes, build her grimoire: her own book
tool, her sigils reusable by page name, and grimoire pages she can show in videos").

A book the office KEEPS and she WRITES. Nothing is written into it for her: it starts empty, every page is hers (tools,
not seeds). A page has a title, a kind (sigil, spell, ritual, recipe, charm, lore, note), her text, and optionally a
sigil -- her own drawing as SVG path strings in a 0-100 box, one string per stroke, drawn in that order.
  - Her sigils are reusable by name: a video part's "sigil" can be the PAGE TITLE, and the office draws that page's sigil.
  - A video part can show a page: "grimoire": "<page title>" -> a book-page card (cards/grimoire.html): aged paper,
    her title, her sigil drawn in ink stroke by stroke, her words written in.
Stored per seat in data/grimoire/<office>.json. Only her seat is granted the tool.
"""
from __future__ import annotations

import datetime
import json
import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(_ROOT, "data", "grimoire")
KINDS = ("sigil", "spell", "ritual", "recipe", "charm", "lore", "note")
MAX_PAGES = 300
MAX_TEXT = 6000

GRIMOIRE_TOOL = {
    "type": "function",
    "function": {
        "name": "grimoire",
        "description": (
            "YOUR GRIMOIRE: your own book of shadows, kept by the office, written only by you. It started empty. "
            "Actions: \"list\" (every page title and kind); \"read\" (title) -- a page word for word; \"add_page\" "
            "(title, kind, text, and optionally sigil) -- a new page; \"revise_page\" (title, and the text and/or "
            "sigil to replace) -- rewrite a page; \"remove_page\" (title). A page's \"sigil\" is YOUR OWN design: SVG "
            "path strings in a 0-100 box, one string per stroke, drawn in that order (\"M 50 8 L 50 92\" is a line; "
            "A for arcs, C/Q for curves). Your sigil pages are reusable in videos by their title (a part's \"sigil\": "
            "\"<page title>\"), and any page can be shown on screen as a real book page (a part's \"grimoire\": "
            "\"<page title>\"). Your sigil research is on your shelf; read it before you design."),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "read", "add_page", "revise_page", "remove_page"]},
                "title": {"type": "string"},
                "kind": {"type": "string", "enum": list(KINDS)},
                "text": {"type": "string", "description": "The page, in your words."},
                "sigil": {"type": "array", "items": {"type": "string"},
                          "description": "Your sigil: SVG path strings in a 0-100 box, one per stroke, in order."},
            },
            "required": ["action"],
        },
    },
}


def _path(office: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", office or "unknown")
    return os.path.join(DIR, f"{safe}.json")


def _load(office: str) -> dict:
    try:
        with open(_path(office), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) and isinstance(data.get("pages"), list) else {"pages": []}
    except (OSError, ValueError):
        return {"pages": []}


def _save(office: str, data: dict) -> None:
    os.makedirs(DIR, exist_ok=True)
    tmp = _path(office) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, _path(office))


def _key(title: str) -> str:
    return " ".join(str(title or "").lower().split())


def find(office: str, title: str) -> dict | None:
    k = _key(title)
    return next((p for p in _load(office)["pages"] if _key(p.get("title")) == k), None) if k else None


def sigil_of(office: str, title: str) -> list[str]:
    """The sigil drawn on her page `title` (empty if none)."""
    page = find(office, title)
    return list(page.get("sigil") or []) if page else []


def _clean_sigil(sigil) -> tuple[list[str], str | None]:
    import fx
    return fx.sigil_paths(sigil)


def run(office: str, a: dict) -> dict:
    a = a if isinstance(a, dict) else {}
    action = str(a.get("action") or "list").strip().lower()
    data = _load(office)
    pages = data["pages"]
    title = " ".join(str(a.get("title") or "").split())[:120]
    now = datetime.datetime.now().isoformat(timespec="minutes")
    if action == "list":
        return {"pages": [{"title": p["title"], "kind": p.get("kind"), "has_sigil": bool(p.get("sigil"))} for p in pages],
                "count": len(pages),
                "note": "Your book is empty -- every page in it will be yours." if not pages else ""}
    if not title:
        return {"error": "give the page a title"}
    page = next((p for p in pages if _key(p.get("title")) == _key(title)), None)
    if action == "read":
        return page or {"error": f"no page titled {title!r}", "pages": [p["title"] for p in pages]}
    if action == "remove_page":
        if not page:
            return {"error": f"no page titled {title!r}"}
        pages.remove(page)
        _save(office, data)
        return {"removed": title}
    text = str(a.get("text") or "").strip()
    sigil, bad = _clean_sigil(a.get("sigil")) if a.get("sigil") else ([], None)
    if bad:
        return {"error": f"this sigil stroke is not an SVG path in a 0-100 box: {bad!r} -- each stroke starts with M "
                         f"and uses only path letters and numbers"}
    if action == "add_page":
        if page:
            return {"error": f"a page titled {title!r} already exists -- revise_page it, or pick another title"}
        if not text and not sigil:
            return {"error": "a page needs text, a sigil, or both"}
        if len(pages) >= MAX_PAGES:
            return {"error": f"the book holds {MAX_PAGES} pages"}
        kind = a.get("kind") if a.get("kind") in KINDS else ("sigil" if sigil and not text else "note")
        pages.append({"title": title, "kind": kind, "text": text[:MAX_TEXT], "sigil": sigil, "made": now, "revised": now})
        _save(office, data)
        return {"added": title, "kind": kind, "strokes": len(sigil), "pages": len(pages),
                "use": (f'In a video: "sigil": "{title}" draws this sigil as you cast it; "grimoire": "{title}" shows '
                        f'this page as a book page.')}
    if action == "revise_page":
        if not page:
            return {"error": f"no page titled {title!r}"}
        if text:
            page["text"] = text[:MAX_TEXT]
        if sigil:
            page["sigil"] = sigil
        if a.get("kind") in KINDS:
            page["kind"] = a["kind"]
        page["revised"] = now
        _save(office, data)
        return {"revised": title, "strokes": len(page.get("sigil") or [])}
    return {"error": f"unknown action {action!r}"}
