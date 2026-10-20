"""THE LIBRARY -- books the agents can reach for, kept OUT of their brains (2026-09-24).

Barry: "why not make a brain called books that the agents can reach for or a storage, not a brain" -- after
three of his books for Ilnora (306 + 77 + 42 pages) would have put ~300 entries into her always-on skill list.

Layout (all local, nothing leaves the machine):
  data/library/<book-slug>/book.json      {"title", "author", "year", "pages", "readers": [office names] | ["*"],
                                           "trust": "...", "sections": [{"id", "title", "pages", "keywords", "file"}]}
  data/library/<book-slug>/NNN.txt        one section's text
A book is visible only to the offices in its "readers" list ("*" = every seat). Search scores section titles and
keywords first, then the text; read returns one section in full (capped), with the book's trust note on top.
"""
from __future__ import annotations

import json
import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIBRARY = os.path.join(_ROOT, "data", "library")
READ_CAP = 14000
_STOP = {"the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with", "how", "what", "is", "are", "my",
         "do", "does", "can", "i", "you", "it", "about", "from", "by", "be", "use", "used", "using", "make"}


def _tok(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9']+", (text or "").lower()) if t not in _STOP and len(t) > 1]


def _stem(t: str) -> str:
    """Plural -> singular, gently: remedies -> remedy, tinctures -> tincture, burns -> burn (grass stays grass)."""
    if t.endswith("ies") and len(t) > 4:
        return t[:-3] + "y"
    if t.endswith("s") and not t.endswith("ss") and len(t) > 3:
        return t[:-1]
    return t


def books(office_name: str | None = None) -> list[dict]:
    out = []
    if not os.path.isdir(LIBRARY):
        return out
    for slug in sorted(os.listdir(LIBRARY)):
        p = os.path.join(LIBRARY, slug, "book.json")
        if not os.path.isfile(p):
            continue
        b = json.load(open(p, encoding="utf-8"))
        readers = [r.lower() for r in b.get("readers", [])]
        if office_name is None or "*" in readers or office_name.lower() in readers:
            b["slug"] = slug
            out.append(b)
    return out


def catalogue(office_name: str) -> dict:
    return {"books": [{"book": b["slug"], "title": b["title"], "author": b.get("author", ""),
                       "sections": len(b.get("sections", []))} for b in books(office_name)]}


def search(office_name: str, query: str, max_results: int = 6) -> dict:
    q = {_stem(t) for t in _tok(query)}
    if not q:
        return {"error": "Give words to look for, e.g. 'yarrow' or 'burns' or 'salve'."}
    hits = []
    for b in books(office_name):
        for s in b.get("sections", []):
            title = {_stem(t) for t in _tok(s["title"])}
            tags = {_stem(t) for t in _tok(" ".join(s.get("keywords", [])))} - title
            score = 10 * len(q & title) + 4 * len(q & tags)      # its own title beats a tag beats the text
            path = os.path.join(LIBRARY, b["slug"], s["file"])
            text = open(path, encoding="utf-8").read() if os.path.isfile(path) else ""
            body = [_stem(t) for t in _tok(text)]
            counts = {t: body.count(t) for t in q}
            score += sum(min(c, 5) for c in counts.values())
            if not score:
                continue
            first = next((m.start() for t in q for m in [re.search(re.escape(t), text.lower())] if m), 0)
            snippet = " ".join(text[max(0, first - 120): first + 280].split())
            hits.append({"score": score, "book": b["slug"], "book_title": b["title"], "section": s["id"],
                         "title": s["title"], "pages": s.get("pages", ""), "snippet": snippet})
    hits.sort(key=lambda h: -h["score"])
    if not hits:
        return {"results": [], "note": "Nothing in your library matches. " + json.dumps(catalogue(office_name))}
    return {"results": hits[:max(1, min(int(max_results or 6), 12))],
            "how_to_read": "read_library(book, section) gives the full section."}


def read(office_name: str, book: str, section) -> dict:
    for b in books(office_name):
        if b["slug"] != book and b["title"].lower() != str(book).lower():
            continue
        for s in b.get("sections", []):
            if str(s["id"]) == str(section) or s["title"].lower() == str(section).lower():
                text = open(os.path.join(LIBRARY, b["slug"], s["file"]), encoding="utf-8").read()
                cut = len(text) > READ_CAP
                return {"book": b["title"], "author": b.get("author", ""), "year": b.get("year", ""),
                        "section": s["title"], "pages": s.get("pages", ""), "trust": b.get("trust", ""),
                        "text": text[:READ_CAP] + ("\n[... section continues; ask for the next part]" if cut else "")}
        return {"error": f"No section '{section}' in {b['title']}. Use search_library to find the right one."}
    return {"error": f"No book '{book}' on your shelf.", **catalogue(office_name)}
