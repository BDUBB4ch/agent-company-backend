"""
Real live web search for agents that need current info they can't be
expected to know (prices, competitor moves, current regulations, news) --
called as a tool from llm_router.py's tool-calling loop, not hit directly
by any HTTP endpoint.

DUCKDUCKGO ONLY, AND THAT IS A HARD RULE. Barry, 2026-09-07: "duck duck go
period" / "i hate google, i dont want them nowhere near any of my private
shit." Bing was removed entirely the same day -- not disabled, not left as a
fallback, DELETED -- because dead code for a search engine he has banned is a
switch someone flips later by accident. This supersedes his own 2026-09-02
instruction ("search using microsoft or chrome"), which he gave during the
week DDG was serving bot challenges.

DO NOT ADD ANOTHER ENGINE. If DDG is rate-limited, search returns NO RESULTS
and the agent says so out loud -- it never quietly asks someone else, and it
never invents findings. That trade is deliberate and it is his.

This is a scrape, not an official API, and best-effort: if the markup changes
or the site is unreachable it fails soft with an error string -- the same
"never crash the whole turn over an optional capability" pattern as
update_checker.py. The engine that answered is reported in the result so a
bluff ("I searched") can be checked in the traces.
"""
import html as _html
import re

import httpx
from bs4 import BeautifulSoup

DDG_URL = "https://html.duckduckgo.com/html/"
MAX_RESULTS = 5

# SEARXNG FIRST (2026-09-15, Barry: "go, bring searxng back" -- then "yes,
# just duck, remove them totally"). The local SearXNG (tools/searxng,
# 127.0.0.1:8080, see scripts/start_searxng.ps1) runs ONE engine,
# DuckDuckGo, safe search off, and hands back clean JSON instead of scraped
# HTML. Brave and Mojeek were configured for one evening and removed on his
# word: every search leaves the machine once, to DuckDuckGo, exactly as the
# scrape below always did. If the service is down or returns nothing
# usable, that scrape runs as before -- the office never loses search
# because a local service died.
from config import SEARXNG_URL
SEARX_TIMEOUT = 9.0


async def _searx(client: httpx.AsyncClient, query: str, max_results: int) -> tuple[list[dict], list[str]]:
    resp = await client.get(f"{SEARXNG_URL}/search",
                            params={"q": query, "format": "json", "safesearch": "0"},
                            timeout=SEARX_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    out, engines = [], []
    for r in data.get("results", [])[:max_results]:
        if not r.get("url"):
            continue
        out.append({"title": _clean(r.get("title", "")), "url": r.get("url", ""),
                    "snippet": _clean(r.get("content", "") or "")})
        for e in (r.get("engines") or [r.get("engine")] or []):
            if e and e not in engines:
                engines.append(e)
    return out, engines

# A real browser UA + language headers: the HTML endpoint serves a stripped
# page to a bare httpx UA.
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(text or "")).strip()


async def _ddg(client: httpx.AsyncClient, query: str, max_results: int) -> list[dict]:
    # kp=-2 = SAFE SEARCH OFF (2026-09-15, Barry: "i also need the best
    # results. uncensored too"). Without it the HTML endpoint applies DDG's
    # default "moderate" filter on top of Bing's own, so every office search
    # had been quietly filtered. -1 would be "moderate", 1 "strict".
    resp = await client.post(DDG_URL, data={"q": query, "kp": "-2"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    out = []
    for result in soup.select(".result")[:max_results]:
        title_el = result.select_one(".result__title a")
        snippet_el = result.select_one(".result__snippet")
        if title_el is None:
            continue
        out.append({
            "title": _clean(title_el.get_text()),
            "url": title_el.get("href", ""),
            "snippet": _clean(snippet_el.get_text()) if snippet_el else "",
        })
    return out


_STOP = {"the", "a", "an", "of", "for", "and", "or", "in", "on", "to", "with", "is", "are",
         "what", "how", "best", "near", "me", "vs", "low", "high", "new", "top"}


def _looks_relevant(query: str, results: list[dict]) -> bool:
    """At least one result must share a real query word (4+ letters, not a
    stopword) in its title, snippet or URL. Cheap, and it is exactly the test
    the decoy pages fail."""
    words = {w for w in re.findall(r"[a-z0-9]{4,}", (query or "").lower()) if w not in _STOP}
    if not words:
        return True
    for r in results:
        hay = " ".join((r.get("title") or "", r.get("snippet") or "", r.get("url") or "")).lower()
        if any(w in hay for w in words):
            return True
    return False


async def search_web(query: str, max_results: int = MAX_RESULTS) -> dict:
    return await _search_web(query, max_results)


async def _search_web(query: str, max_results: int = MAX_RESULTS) -> dict:
    """Returns {"results": [{"title", "url", "snippet"}, ...], "engine":
    "duckduckgo"} on success, or {"error": "..."} if DuckDuckGo could not
    answer. There is no second engine on purpose -- see the module docstring."""
    query = query.strip()
    if not query:
        return {"error": "Empty search query."}

    async with httpx.AsyncClient(timeout=12.0, headers=_HEADERS,
                                 follow_redirects=True) as client:
        # 1. the local metasearch (Brave + DuckDuckGo + Mojeek merged)
        try:
            sx, engines = await _searx(client, query, max_results)
            if sx and _looks_relevant(query, sx):
                return {"results": sx, "engine": "searxng(" + ",".join(engines or ["?"]) + ")"}
            print(f"[search] searxng answered with nothing usable for {query!r} -- falling back to duckduckgo")
        except (httpx.HTTPError, ValueError) as e:
            print(f"[search] searxng unavailable ({type(e).__name__}) -- falling back to duckduckgo")
        # 2. the DuckDuckGo scrape, unchanged
        try:
            results = await _ddg(client, query, max_results)
        except httpx.HTTPError as e:
            return {"error": (f"DuckDuckGo could not be reached for '{query}' ({e}). "
                              "Say so plainly -- do not invent what a search would "
                              "have shown, and do not try another search engine.")}

    if results and _looks_relevant(query, results):
        return {"results": results, "engine": "duckduckgo"}

    why = ("DuckDuckGo returned results that do not match the query"
           if results else "DuckDuckGo returned no results")
    return {"error": (f"No web results found for '{query}' ({why}). "
                      "Say so plainly -- do not invent what a search would have "
                      "shown, and do not try another search engine.")}
