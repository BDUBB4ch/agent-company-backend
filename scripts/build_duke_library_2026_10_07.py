"""Dr. Duke's Phytochemical and Ethnobotanical Databases (USDA ARS, public domain CC0, Ag Data Commons
doi 10.15482/USDA.ADC/1239279) -> Ilnora's library (Barry 2026-10-07: "do all four. i want all the stuff").
One section per plant that has recorded traditional uses: names, family, uses by country (with source), main
chemicals by plant part, doses where recorded. Source CSVs: data/plantdata/duke/."""
import collections
import csv
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "plantdata", "duke")
OUT = os.path.join(ROOT, "data", "library", "dr-dukes-ethnobotany")
csv.field_size_limit(10 ** 7)


def rows(name: str):
    with open(os.path.join(SRC, name), encoding="latin-1", newline="") as fh:
        yield from csv.DictReader(fh)


def slug(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


tax = {r["FNFNUM"]: r for r in rows("FNFTAX.csv")}
by_taxon = {r["TAXON"].strip().lower(): r["FNFNUM"] for r in tax.values() if r.get("TAXON")}
common = collections.defaultdict(set)
for r in rows("COMMON_NAMES.csv"):
    if r.get("CNNAM"):
        common[r["FNFNUM"]].add(r["CNNAM"].strip())
parts = {r[next(iter(r))]: list(r.values())[1] for r in rows("PARTS.csv")} if os.path.isfile(os.path.join(SRC, "PARTS.csv")) else {}

ethno = collections.defaultdict(list)
for r in rows("ETHNOBOT.csv"):
    taxon = (r.get("TAXON") or f"{r.get('GENUS', '')} {r.get('SPECIES', '')}").strip()
    if not taxon or not r.get("ACTIVITY"):
        continue
    ethno[taxon].append((r["ACTIVITY"].strip(), (r.get("COUNTRY") or "").strip(), (r.get("CNAME") or "").strip(),
                         (r.get("REFERENCE") or "").strip(), r.get("FAMILY") or ""))

chems = collections.defaultdict(lambda: collections.defaultdict(set))
for r in rows("FARMACY_NEW.csv"):
    if r.get("CHEM"):
        chems[r["FNFNUM"]][r.get("PPCO") or "?"].add(r["CHEM"].strip().title())

dosage = collections.defaultdict(list)
if os.path.isfile(os.path.join(SRC, "DOSAGE.csv")):
    for r in rows("DOSAGE.csv"):
        key = r.get("FNFNUM") or ""
        txt = " ".join(v for k, v in r.items() if v and k not in ("FNFNUM", "USERID", "CREATED", "MODIFIED"))
        if key and txt:
            dosage[key].append(txt[:300])

os.makedirs(OUT, exist_ok=True)
sections = []
for n, taxon in enumerate(sorted(ethno), 1):
    uses = ethno[taxon]
    fnf = by_taxon.get(taxon.lower(), "")
    fam = (tax.get(fnf, {}).get("FAMILY") or next((u[4] for u in uses if u[4]), "")).strip()
    names = sorted(common.get(fnf, set()) | {u[2] for u in uses if u[2]})
    by_use = collections.defaultdict(set)
    for act, country, _c, ref, _f in uses:
        by_use[act].add((country or "unspecified", ref))
    lines = [f"{taxon}" + (f" ({fam})" if fam else ""),
             "Common names: " + (", ".join(names[:25]) if names else "none recorded"), "",
             "TRADITIONAL USES (ethnobotany -- where and per which source):"]
    for act in sorted(by_use):
        where = sorted(by_use[act])
        lines.append(f"- {act}: " + "; ".join(f"{c} ({r})" if r else c for c, r in where[:8])
                     + (f" ... +{len(where) - 8} more" if len(where) > 8 else ""))
    if fnf and chems.get(fnf):
        lines += ["", "CHEMICALS BY PLANT PART (part code: chemicals):"]
        for pp, cs in sorted(chems[fnf].items()):
            cs = sorted(cs)
            lines.append(f"- {pp}: " + ", ".join(cs[:40]) + (f" ... +{len(cs) - 40} more" if len(cs) > 40 else ""))
    if fnf and dosage.get(fnf):
        lines += ["", "DOSAGE RECORDS:"] + [f"- {d}" for d in dosage[fnf][:10]]
    lines += ["", "Source: Dr. Duke's Phytochemical and Ethnobotanical Databases, USDA Agricultural Research Service "
                  "(public domain). Traditional uses are what people used it for -- not proof it works; label believed "
                  "vs proven."]
    sid = f"{n:05d}"
    open(os.path.join(OUT, f"{sid}.txt"), "w", encoding="utf-8").write("\n".join(lines))
    kw = {taxon.lower(), taxon.split()[0].lower(), fam.lower()} | {x.lower() for x in names[:25]}
    kw |= {a.lower() for a in list(by_use)[:60]}
    sections.append({"id": sid, "title": taxon + (f" -- {names[0]}" if names else ""), "pages": "",
                     "keywords": sorted(k for k in kw if k), "file": f"{sid}.txt"})

book = {"title": "Dr. Duke's Phytochemical and Ethnobotanical Databases (USDA)", "author": "James A. Duke, USDA ARS",
        "year": 2025, "pages": len(sections), "readers": ["ilnora"],
        "trust": "Official USDA research database (public domain). Traditional-use records are ethnobotany (what "
                 "people used plants for, per the cited source), NOT clinical proof -- label believed vs proven. "
                 "Chemical lists are measured constituents.",
        "sections": sections}
json.dump(book, open(os.path.join(OUT, "book.json"), "w", encoding="utf-8"), ensure_ascii=False)
print(len(sections), "plants written to", OUT)
