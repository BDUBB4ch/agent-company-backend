"""REAL PLANT PHOTOS for Ilnora's videos (2026-09-24). Barry: "the plants need to be of the plants shes talking
about, no other way" -- after the picture engine drew "mugwort" as a cannabis-looking plant.

Photos come ONLY from Barry's drop folder -- drop/Plants/<scientific name>/  (jpg / png / webp). Nothing is
fetched from the internet (Barry, 2026-09-24: no Wikimedia -- it requires sending a contact with every request).
Optional drop/Plants/<scientific name>/credits.txt: one line per photo, "filename | credit line", for photos that
need attribution in the post description.
"""
from __future__ import annotations

import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLANTS_DIR = os.path.join(_ROOT, "drop", "Plants")
_EXT = (".jpg", ".jpeg", ".png", ".webp")


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


def folder_for(species: str) -> str | None:
    """The drop folder for a species -- matched case-insensitively, ignoring punctuation."""
    if not os.path.isdir(PLANTS_DIR):
        return None
    want = _norm(species)
    for entry in os.listdir(PLANTS_DIR):
        p = os.path.join(PLANTS_DIR, entry)
        if os.path.isdir(p) and _norm(entry) == want:
            return p
    return None


# NO BURNED-IN TEXT (2026-10-18, Henbane Short: the iNaturalist photo the office picked carried the photographer's own
# caption -- a name, a town, GPS coordinates and a date -- and it went out in part 1 and behind the fact card). Every
# photo is read once by RapidOCR (ocr.py, CPU) and one with real text on it is skipped; the verdict is cached per file
# in .ocr_cache.json so a folder is read once, not per build.
_TEXT_TOKENS = re.compile(r"[A-Za-z]{3,}|\d{2,}")
_OCR_MIN_TOKENS = 3


def _has_burned_text(path: str) -> bool:
    import json
    cache_path = os.path.join(os.path.dirname(path), ".ocr_cache.json")
    try:
        cache = json.load(open(cache_path, encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    key = os.path.basename(path).lower()
    if key in cache:
        return bool(cache[key]["text"])
    try:
        import ocr
        with open(path, "rb") as fh:
            found = ocr.read_image(fh.read()) or ""
        tokens = _TEXT_TOKENS.findall(found)
        verdict = len(tokens) >= _OCR_MIN_TOKENS
        cache[key] = {"text": verdict, "read": found[:200]}
        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, ensure_ascii=False, indent=1)
        return verdict
    except Exception:  # noqa: BLE001 -- OCR unavailable = never block a photo
        return False


def photos(species: str, allow_text: bool = False) -> list[dict]:
    """All photos Barry has dropped for `species`: [{"path", "credit"}], minus any with text burned in. Empty if none."""
    d = folder_for(species)
    if not d:
        return []
    credits = {}
    cp = os.path.join(d, "credits.txt")
    if os.path.isfile(cp):
        for line in open(cp, encoding="utf-8"):
            if "|" in line:
                f, c = line.split("|", 1)
                credits[f.strip().lower()] = c.strip()
    out = [{"path": os.path.join(d, f), "credit": credits.get(f.lower(), "")}
           for f in sorted(os.listdir(d)) if f.lower().endswith(_EXT)]
    if allow_text:
        return out
    return [p for p in out if not _has_burned_text(p["path"])]


# iNATURALIST (2026-10-08, Barry: "yes to iNaturalist" -- after Qwen-Image drew bloodroot as a pink five-petal
# flower and Bonsai described it as yellow). Public API, no key, nothing about Barry sent. Only CC0 / CC BY / CC BY-SA
# photos from research-grade observations; the attribution line goes in credits.txt -> the post description.
INAT = "https://api.inaturalist.org/v1"
INAT_LICENSES = "cc0,cc-by,cc-by-sa"
INAT_COUNT = 3


def fetch_inaturalist(species: str, count: int = INAT_COUNT, log=print) -> list[dict]:
    """Download up to `count` CC photos of `species` into drop/Plants/<species>/ (with credits.txt). Returns
    photos(species) afterwards. Never raises -- an empty list means the picture engine draws it as before."""
    import json
    import urllib.parse
    import urllib.request
    try:
        import memory
        if memory.is_offline_mode():
            return []
    except Exception:  # noqa: BLE001
        pass

    def get(url: str) -> dict:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=25) as r:
            return json.load(r)

    try:
        q = urllib.parse.urlencode({"q": species, "rank": "species", "per_page": 1})
        taxa = get(f"{INAT}/taxa?{q}").get("results") or []
        taxon = next((t for t in taxa if _norm(t.get("name", "")) == _norm(species)), None)
        if not taxon:
            log(f"iNaturalist: no exact taxon for {species}")
            return []
        q = urllib.parse.urlencode({"taxon_id": taxon["id"], "photos": "true", "quality_grade": "research",
                                    "photo_license": INAT_LICENSES, "per_page": 30, "order_by": "votes",
                                    "order": "desc"})
        obs = get(f"{INAT}/observations?{q}").get("results") or []
    except Exception as exc:  # noqa: BLE001
        log(f"iNaturalist lookup failed for {species}: {type(exc).__name__}")
        return []
    folder = folder_for(species) or os.path.join(PLANTS_DIR, species)
    os.makedirs(folder, exist_ok=True)
    have = [f for f in os.listdir(folder) if f.lower().endswith(_EXT)]
    credits = []
    got = 0
    for o in obs:
        if got >= count:
            break
        for p in o.get("photos") or []:
            lic = (p.get("license_code") or "").lower()
            if lic not in INAT_LICENSES.split(",") or not p.get("url"):
                continue
            url = p["url"].replace("/square.", "/large.")
            name = f"inat_{p['id']}{os.path.splitext(urllib.parse.urlparse(url).path)[1] or '.jpg'}"
            if name in have:
                got += 1
                break
            try:
                with urllib.request.urlopen(urllib.request.Request(url), timeout=30) as r:
                    data = r.read()
                if len(data) < 20_000:
                    continue
                with open(os.path.join(folder, name), "wb") as fh:
                    fh.write(data)
            except Exception:  # noqa: BLE001
                continue
            attribution = p.get("attribution") or f"iNaturalist photo {p['id']} ({lic.upper()})"
            credits.append(f"{name} | Photo: {attribution}, via iNaturalist")
            got += 1
            break
    if credits:
        with open(os.path.join(folder, "credits.txt"), "a", encoding="utf-8") as fh:
            fh.write("\n".join(credits) + "\n")
        log(f"iNaturalist: {len(credits)} photo(s) of {species} saved to drop/Plants")
    return photos(species)


def missing(species_list: list[str]) -> list[str]:
    """Species named in a video that have no photos yet (what to ask Barry for)."""
    return sorted({s for s in species_list if not photos(s)})
