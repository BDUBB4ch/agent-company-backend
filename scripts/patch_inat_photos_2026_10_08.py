r"""One-off patch (2026-10-08, Barry: "yes to iNaturalist"): real plant photos from iNaturalist's public API when he
has not dropped any -- Creative Commons only (CC0 / CC BY / CC BY-SA), research-grade observations, the
photographer's attribution line kept in credits.txt and carried into the post description by reel_builder.
No account, no key, no contact sent (plain default User-Agent). Skipped in offline mode."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def patch(path, pairs):
    t = open(path, encoding="utf-8").read()
    for a, b in pairs:
        assert t.count(a) == 1, (os.path.basename(path), a[:60])
        t = t.replace(a, b)
    open(path, "w", encoding="utf-8").write(t)
    print("ok", os.path.basename(path))


patch(os.path.join(ROOT, "backend", "plant_photos.py"), [
(r'''def missing(species_list: list[str]) -> list[str]:''',
r'''# iNATURALIST (2026-10-08, Barry: "yes to iNaturalist" -- after Qwen-Image drew bloodroot as a pink five-petal
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


def missing(species_list: list[str]) -> list[str]:'''),
])

patch(os.path.join(ROOT, "backend", "reel_builder.py"), [
(r'''    for species, prompt in jobs:
        mine = plant_photos.photos(species)
        if mine:''',
r'''    for species, prompt in jobs:
        mine = plant_photos.photos(species) or plant_photos.fetch_inaturalist(species, log=log)   # 2026-10-08
        if mine:'''),
])
