"""RESEARCH TOOLS FOR REAL SOURCES (2026-09-24, Barry: "she also needs to have documents from labs, scientists,
universities and other places about healing herbs" / "the ones that are free to read, but not download to her
brain, how do we teach it to her as info not gold").

  read_web_page(url)  -- read ONE public web page as plain text, so a source can be read in full (search_web only
                          ever returned snippets). Facts can be learned from it; the author's wording is theirs --
                          the result carries that instruction every time.
  pubmed_search(query) -- the US National Library of Medicine's index of 36M+ studies (NCBI E-utilities, free, no key,
                          no account). Only the search words leave the machine.

Guards: http/https only; never Google (his rule); the words 'google'/'gstatic' below are the BLOCKLIST of hostnames
this tool refuses to contact (see _BLOCKED_HOST_RE), not names it calls -- a plain-text scan flagging them is a
false alarm, the code is already doing what the rule wants. Never localhost / private / link-local addresses
(nothing on his own network, checked after DNS and after every redirect); 3 MB cap; 12,000 chars returned.
Never raises.
Both are OUTBOUND, so offline mode strips them (main._OFFLINE_STRIPPED_NAMES).
"""
from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

import httpx

MAX_BYTES = 3_000_000
MAX_CHARS = 12_000
_BLOCKED_HOST_RE = re.compile(r"(^|\.)(google|googleapis|gstatic|googleusercontent|youtube)\.", re.I)
LEARN_NOTE = ("This is someone else's writing. Learn the FACTS from it: put them in your own words, label the "
              "evidence (PROVEN / SUPPORTED / TRADITIONAL), and name the source with its link. Never paste the "
              "author's paragraphs or tables into your notes, posts or answers. To keep what you learned, save a "
              "short note in your own words with the source (save_note).")


def _safe_host(url: str) -> str | None:
    """None if fine, else the reason it is refused."""
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return "only http/https web pages can be read"
    host = p.hostname.lower()
    if _BLOCKED_HOST_RE.search(host + "."):
        return "Google and its services are never used in this office"
    if host in ("localhost",) or host.endswith(".local"):
        return "pages on this computer or its network cannot be read"
    try:
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return "pages on this computer or its network cannot be read"
    except (socket.gaierror, ValueError):
        return "that address could not be found"
    return None


def _text_from_html(html: str) -> tuple[str, str]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    for t in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg"]):
        t.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    lines = []
    for el in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "th", "dt", "dd"]):
        txt = " ".join(el.get_text(" ", strip=True).split())
        if len(txt) >= 3:
            lines.append(("## " + txt) if el.name in ("h1", "h2", "h3") else txt)
    text = "\n".join(dict.fromkeys(lines))          # drop repeated nav/table fragments
    return title, text


def read_web_page(url: str) -> dict:
    url = (url or "").strip()
    why = _safe_host(url)
    if why:
        return {"error": f"Cannot read {url!r}: {why}."}
    try:
        with httpx.Client(timeout=25, follow_redirects=False,
                          headers={"User-Agent": "Mozilla/5.0 (research reader)"}) as c:
            for _ in range(5):                       # follow redirects ourselves so each hop is re-checked
                r = c.get(url)
                if r.is_redirect and r.headers.get("location"):
                    url = str(httpx.URL(url).join(r.headers["location"]))
                    why = _safe_host(url)
                    if why:
                        return {"error": f"The page redirected somewhere that cannot be read: {why}."}
                    continue
                break
        if r.status_code >= 400:
            return {"error": f"The page answered HTTP {r.status_code}.", "url": url}
        data = r.content[:MAX_BYTES]
        ctype = r.headers.get("content-type", "").lower()
        if "pdf" in ctype or url.lower().endswith(".pdf"):
            import document_extract
            title, text = url.rsplit("/", 1)[-1], document_extract.extract_text("page.pdf", data)
        else:
            title, text = _text_from_html(data.decode(r.encoding or "utf-8", errors="replace"))
        text = text.strip()
        if not text:
            return {"error": "No readable text on that page.", "url": url}
        clipped = len(text) > MAX_CHARS
        return {"url": url, "title": title, "text": text[:MAX_CHARS],
                "clipped": clipped, "chars": len(text), "how_to_use": LEARN_NOTE}
    except Exception as exc:                          # noqa: BLE001
        return {"error": f"Could not read the page: {type(exc).__name__}: {str(exc)[:160]}"}


_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_STRONG = ("(systematic review[pt] OR meta-analysis[pt] OR randomized controlled trial[pt] OR review[pt])")


def pubmed_search(query: str, max_results: int = 5, strong_studies_only: bool = True) -> dict:
    """Real studies from PubMed: title, journal, year, study type, abstract (trimmed), link."""
    q = (query or "").strip()
    if not q:
        return {"error": "Give the search words (e.g. 'calendula wound healing')."}
    term = f"({q}) AND {_STRONG}" if strong_studies_only else q
    n = max(1, min(int(max_results or 5), 10))
    try:
        with httpx.Client(timeout=25) as c:
            s = c.get(f"{_EUTILS}/esearch.fcgi", params={"db": "pubmed", "term": term, "retmax": n,
                                                          "sort": "relevance", "retmode": "json",
                                                          "tool": "herbal-research"}).json()
            ids = s.get("esearchresult", {}).get("idlist", [])
            total = s.get("esearchresult", {}).get("count", "0")
            if not ids:
                return {"query": q, "found": 0, "studies": [],
                        "note": "No studies matched. Try fewer or plainer words, or strong_studies_only=false."}
            x = c.get(f"{_EUTILS}/efetch.fcgi", params={"db": "pubmed", "id": ",".join(ids), "retmode": "xml",
                                                         "tool": "herbal-research"}).text
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(x, "xml")
        out = []
        for art in soup.find_all("PubmedArticle"):
            pmid = art.find("PMID").get_text() if art.find("PMID") else ""
            title = " ".join(art.find("ArticleTitle").get_text(" ").split()) if art.find("ArticleTitle") else ""
            journal = art.find("Title").get_text() if art.find("Title") else ""
            year = (art.find("PubDate").find("Year").get_text()
                    if art.find("PubDate") and art.find("PubDate").find("Year") else "")
            types = [t.get_text() for t in art.find_all("PublicationType")][:3]
            abstract = " ".join(" ".join(a.get_text(" ").split()) for a in art.find_all("AbstractText"))
            out.append({"pmid": pmid, "title": title, "journal": journal, "year": year, "type": types,
                        "abstract": abstract[:1400] + ("..." if len(abstract) > 1400 else ""),
                        "link": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"})
        return {"query": q, "found": int(total), "shown": len(out), "studies": out,
                "how_to_use": ("Real published studies. Say what they found in your own words with the study "
                               "type, year and link (a 2021 meta-analysis of 12 trials found...). An abstract is a "
                               "summary -- say so if you only read the abstract. " + LEARN_NOTE.split('. ', 1)[1])}
    except Exception as exc:                          # noqa: BLE001
        return {"error": f"PubMed could not be reached: {type(exc).__name__}: {str(exc)[:160]}"}
