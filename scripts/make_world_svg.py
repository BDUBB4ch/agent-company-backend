"""2026-10-17: build data/video_queue/cards/world.svg for Ilnora's map card from a Natural Earth admin-0 countries
GeoJSON (public domain; 110m is enough -- ~250 KB). One <path> per country, equirectangular, with data-name,
data-continent, data-iso and data-aliases so the card can light up what she names.
Usage: venv/Scripts/python.exe scripts/make_world_svg.py <countries.geojson> [out.svg]
No network: the GeoJSON is a file Barry OK'd and downloaded once."""
import json
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "video_queue", "cards", "world.svg")
W, H = 2000, 1000           # viewBox; equirectangular, lon -180..180 -> 0..W, lat 90..-90 -> 0..H

# the words she is likely to write that are not the dataset's names
ALIASES = {
    "United States of America": "united states|usa|us|america|the states",
    "United Kingdom": "uk|britain|great britain|england|scotland|wales",
    "Russia": "siberia",
    "China": "prc",
    "Iran": "persia",
    "Turkey": "türkiye|anatolia|asia minor",
    "Myanmar": "burma",
    "Czechia": "czech republic",
    "Democratic Republic of the Congo": "congo|drc|zaire",
    "Republic of the Congo": "congo-brazzaville",
    "eSwatini": "swaziland",
    "Taiwan": "formosa",
    "South Korea": "korea",
    "North Korea": "korea",
    "Vietnam": "indochina",
    "Laos": "indochina",
    "Cambodia": "indochina",
    "Greece": "balkans",
    "Mexico": "mesoamerica|central america",
    "Guatemala": "central america|mesoamerica",
    "Honduras": "central america",
    "Nicaragua": "central america",
    "Costa Rica": "central america",
    "Panama": "central america",
    "Belize": "central america",
    "El Salvador": "central america",
    "Peru": "andes|amazon",
    "Bolivia": "andes|amazon",
    "Ecuador": "andes|amazon",
    "Colombia": "andes|amazon",
    "Brazil": "amazon",
    "Egypt": "nile|north africa|levant",
    "Morocco": "north africa|maghreb",
    "Algeria": "north africa|maghreb|sahara",
    "Tunisia": "north africa|maghreb",
    "Libya": "north africa|sahara",
    "Israel": "levant|holy land",
    "Lebanon": "levant",
    "Syria": "levant",
    "Jordan": "levant",
    "Iraq": "mesopotamia",
    "India": "indian subcontinent|south asia|himalayas",
    "Nepal": "himalayas",
    "Bhutan": "himalayas",
    "Pakistan": "indian subcontinent|south asia",
    "Bangladesh": "indian subcontinent|south asia",
    "Sri Lanka": "ceylon",
    "Indonesia": "east indies|spice islands",
    "Madagascar": "malagasy",
    "Australia": "oceania|outback",
    "New Zealand": "aotearoa|oceania",
    "Canada": "north america",
    "Greenland": "arctic",
    "Spain": "iberia|mediterranean",
    "Portugal": "iberia",
    "Italy": "mediterranean",
    "France": "mediterranean|western europe",
    "Germany": "central europe|western europe",
    "Poland": "central europe|eastern europe",
    "Ukraine": "eastern europe",
    "Norway": "scandinavia|nordics",
    "Sweden": "scandinavia|nordics",
    "Finland": "scandinavia|nordics",
    "Denmark": "scandinavia|nordics",
    "Iceland": "nordics",
    "Ethiopia": "horn of africa|east africa",
    "Somalia": "horn of africa|east africa",
    "Kenya": "east africa",
    "Tanzania": "east africa",
    "Uganda": "east africa",
    "South Africa": "southern africa",
    "Nigeria": "west africa",
    "Ghana": "west africa",
    "Senegal": "west africa",
    "Mali": "west africa|sahel|sahara",
    "Niger": "sahel|sahara",
    "Chad": "sahel|sahara",
    "Sudan": "sahel|nile",
    "Kazakhstan": "central asia|steppe",
    "Uzbekistan": "central asia",
    "Mongolia": "steppe|central asia",
    "Afghanistan": "central asia",
    "Saudi Arabia": "arabia|arabian peninsula|middle east",
    "Yemen": "arabia|arabian peninsula",
    "Oman": "arabia|arabian peninsula",
    "Japan": "east asia",
    "Philippines": "southeast asia",
    "Malaysia": "southeast asia",
    "Thailand": "southeast asia|siam",
    "Papua New Guinea": "new guinea|oceania",
}
# continent words beyond the dataset's CONTINENT field
CONTINENT_ALIASES = {
    "North America": "the americas|new world",
    "South America": "the americas|new world|latin america",
    "Europe": "old world",
    "Asia": "old world|the east",
    "Africa": "old world",
    "Oceania": "pacific",
}


def project(lon: float, lat: float) -> tuple[float, float]:
    return (lon + 180.0) * W / 360.0, (90.0 - lat) * H / 180.0


def ring_path(ring) -> str:
    pts = [project(float(x), float(y)) for x, y, *_ in ring]
    if len(pts) < 3:
        return ""
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z"


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src, out = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else OUT)
    data = json.load(open(src, encoding="utf-8"))
    feats = data["features"] if data.get("type") == "FeatureCollection" else [data]
    paths = []
    for f in feats:
        p = f.get("properties") or {}
        name = p.get("NAME") or p.get("ADMIN") or p.get("name") or p.get("admin") or ""
        admin = p.get("ADMIN") or p.get("admin") or name
        cont = p.get("CONTINENT") or p.get("continent") or ""
        iso = (p.get("ISO_A2") or p.get("iso_a2") or p.get("ISO_A2_EH") or "").strip()
        if iso in ("-99", "-1"):
            iso = ""
        if name == "Antarctica":            # a dead slab across the bottom of every card; no plant story lives there
            continue
        g = f.get("geometry") or {}
        polys = g.get("coordinates") or []
        if g.get("type") == "Polygon":
            polys = [polys]
        elif g.get("type") != "MultiPolygon":
            continue
        d = " ".join(ring_path(ring) for poly in polys for ring in poly[:1])   # outer rings only
        if not d:
            continue
        aliases = "|".join(a for a in (ALIASES.get(admin, ""), ALIASES.get(name, ""),
                                       CONTINENT_ALIASES.get(cont, "")) if a)
        attrs = (f' data-name="{name}" data-admin="{admin}" data-continent="{cont}" data-iso="{iso}"'
                 f' data-aliases="{aliases}"').replace("&", "&amp;")
        paths.append(f'<path{attrs} d="{d}"/>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet">\n'
           + "\n".join(paths) + "\n</svg>\n")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(f"wrote {out}: {len(paths)} countries, {os.path.getsize(out) // 1024} KB")


if __name__ == "__main__":
    main()
