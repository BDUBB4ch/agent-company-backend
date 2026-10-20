"""Native American Ethnobotany (Daniel E. Moerman; BRIT naeb.brit.org) -> Ilnora's library (Barry 2026-10-07:
"indiginous American stuff too" / "The native American stuff is real but taken from Black people, Real american
indians. Im blackfoot."). Data: the full table set via the naeb.louispotok.com mirror (data/plantdata/naeb.db).
Private reference only -- never republished; uses are cited to Moerman and the original source.
One section per plant: uses grouped by nation -- category, what was done, source."""
import collections
import json
import os
import re
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "plantdata", "naeb.db")
OUT = os.path.join(ROOT, "data", "library", "native-american-ethnobotany")

c = sqlite3.connect(DB)
tribes = dict(c.execute("select id, name from tribes"))
cats = dict(c.execute("select id, name from use_categories"))
subcats = dict(c.execute("select id, name from use_subcategories"))
sources = {i: (a or "", y or "", t or "") for i, a, y, t in c.execute("select id, author, year, title from sources")}
species = {i: (n, cn or "", fam or "") for i, n, cn, fam in c.execute("select id, name, common_names, family from species")}
uses = collections.defaultdict(list)
for sp, tr, src, pg, cat, sub, notes in c.execute(
        "select species, tribe, source, pageno, use_category, use_subcategory, notes from uses"):
    uses[sp].append((tribes.get(tr, "?"), cats.get(cat, ""), subcats.get(sub, ""), (notes or "").strip(),
                     sources.get(src, ("", "", "")), pg or ""))

os.makedirs(OUT, exist_ok=True)
sections = []
for n, sp in enumerate(sorted(uses, key=lambda s: species.get(s, ("",))[0]), 1):
    name, common, fam = species.get(sp, ("?", "", ""))
    by_tribe = collections.defaultdict(list)
    for tr, cat, sub, notes, (au, yr, ti), pg in uses[sp]:
        cite = f"{au} {yr}".strip() + (f", p.{pg}" if pg else "")
        by_tribe[tr].append(f"[{cat}{' / ' + sub if sub else ''}] {notes}" + (f" ({cite})" if cite else ""))
    lines = [f"{name}" + (f" ({fam})" if fam else ""), f"Common names: {common or 'none recorded'}", "",
             f"USES BY {len(by_tribe)} NATION(S) -- {len(uses[sp])} recorded uses:"]
    for tr in sorted(by_tribe):
        lines.append(f"{tr}:")
        lines += [f"  - {u}" for u in by_tribe[tr][:25]]
        if len(by_tribe[tr]) > 25:
            lines.append(f"  ... +{len(by_tribe[tr]) - 25} more")
    lines += ["", "Source: Daniel E. Moerman, Native American Ethnobotany (database, BRIT naeb.brit.org), citing the "
                  "original ethnographic records above. Traditional uses -- label believed vs proven; credit the "
                  "nation that used it."]
    sid = f"{n:05d}"
    open(os.path.join(OUT, f"{sid}.txt"), "w", encoding="utf-8").write("\n".join(lines))
    kw = {name.lower(), name.split()[0].lower(), fam.lower()}
    kw |= {x.strip().lower() for x in re.split(r"[,;]", common) if x.strip()}
    kw |= {t.lower() for t in by_tribe} | {u[2].lower() for u in uses[sp] if u[2]} | {u[1].lower() for u in uses[sp] if u[1]}
    first = re.split(r"[,;]", common)[0].strip() if common else ""
    sections.append({"id": sid, "title": name + (f" -- {first}" if first else ""), "pages": "",
                     "keywords": sorted(k for k in kw if k), "file": f"{sid}.txt"})

json.dump({"title": "Native American Ethnobotany (Moerman)", "author": "Daniel E. Moerman", "year": 2003,
           "pages": len(sections), "readers": ["ilnora"],
           "trust": "Daniel Moerman's Native American Ethnobotany database: 44,000+ documented uses by 291 nations, "
                    "each cited to the original ethnographic record. Traditional uses (believed); credit the nation "
                    "and the source.",
           "sections": sections}, open(os.path.join(OUT, "book.json"), "w", encoding="utf-8"), ensure_ascii=False)
print(len(sections), "plants ->", OUT)
