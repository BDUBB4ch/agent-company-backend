"""
Web search via a local SearXNG instance (see AgentCompanyBackend/searxng/
docker-compose.yml) -- a second, separate search capability from
web_search.py's DuckDuckGo scrape.

The key difference is how each is wired in:
  - web_search.py's search_web() is registered as an automatic Ollama tool
    (see llm_router.py's WEB_SEARCH_TOOL) -- the model can silently decide
    to call it mid-reasoning, on every single turn, with no explicit ask.
  - web_search() below is deliberately NOT registered that way. It's only
    reachable through POST /api/web_search (see main.py) -- something has
    to explicitly invoke it (the Godot UI, a curl call, a future button),
    the same "draft/propose, nothing happens automatically" pattern as
    image generation and the whole approval queue. No agent can trigger a
    SearXNG search on its own mid-conversation.

This is a real local API (not a scrape), so it fails hard with a clear
exception rather than silently returning nothing -- callers (main.py)
decide how to degrade (e.g. a 503 telling the owner the Docker container
isn't running), same as amuse_integration.py's pattern for AmuseBridge.
"""
import httpx
from config import SEARXNG_URL

MAX_RESULTS = 8


class SearxngUnavailable(Exception):
    """Raised when the local SearXNG container can't be reached at all --
    distinct from 'reachable but zero results', which just returns []."""


async def web_search(query: str, max_results: int = MAX_RESULTS) -> list[dict]:
    """Returns a list of {"title", "url", "snippet"} dicts (possibly empty
    if the query has no results). Raises SearxngUnavailable if the
    container itself can't be reached -- this is an online enhancement,
    not something the rest of the system depends on, so every caller must
    handle that exception rather than assume this always succeeds."""
    query = query.strip()
    if not query:
        return []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{SEARXNG_URL}/search",
                params={"q": query, "format": "json"},
            )
            resp.raise_for_status()
    except httpx.HTTPError as e:
        raise SearxngUnavailable(
            f"Could not reach SearXNG at {SEARXNG_URL} ({e}). Is the Docker "
            f"container running? (docker compose up -d in AgentCompanyBackend/searxng/)"
        ) from e

    try:
        data = resp.json()
    except ValueError as e:
        # Usually means the JSON API isn't actually enabled (missing
        # `search: formats: [html, json]` or a missing/blank secret_key in
        # settings.yml, which makes SearXNG 403 JSON requests) and we got
        # an HTML error page back instead of JSON.
        raise SearxngUnavailable(
            "SearXNG responded, but not with JSON -- check that settings.yml "
            "has `search: formats: [html, json]` and a real secret_key."
        ) from e

    results = []
    for r in data.get("results", [])[:max_results]:
        results.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": r.get("content", ""),
        })
    return results
