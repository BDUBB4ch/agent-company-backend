"""Chunk the 48K Global Garden price list so recall can actually hand it over.

Found 2026-09-17: `global-garden-wholesale-pricelist.md` (fact 651,
business:bdubbgrows) is 48,338 chars against RECALL_BUDGET = 20,000. Recall
injects WHOLE docs and never clips, so it NAMED this file on every non-Bionova
margin question and never once put it in front of anyone; read_skill (~1% of
calls, measured) was the only door. The entire non-Bionova margin map was
effectively unreachable. Same fix as the V8 treatment on 2026-08-20: chunk it
under the budget, one part per product family group, each with its own USE
WHEN carrying the brand names so the right part routes.

Dry-run by default (prints the plan). --apply supersedes fact 651 (never
deleted; content also backed up to data/) and seeds the parts under the SAME
category, so the audience is unchanged. Rows are carried byte-for-byte.
"""
import os
import re
import sys
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))

import memory  # noqa: E402

SOURCE = "global-garden-wholesale-pricelist.md"
CATEGORY = "business:bdubbgrows"
PART_BODY_MAX = 15_000          # body per part; header adds ~1.3K, ceiling 18.5K
MARKER_RE = re.compile(r"^[A-Z][A-Z0-9 &/'\-\.,]{6,}\s*$")

GENERIC_USE_WHEN = (
    "wholesale cost, cost price, what does it cost me, margin on, margins, srp, "
    "suggested retail, price list, pricelist, reprice, repricing, at or below "
    "cost, selling below cost, global garden, gg, supplier price, case qty, "
    "item code, non-bionova product cost, breakeven for the store"
)

HOW_TO_READ = (
    "⚠️ INTERNAL AND CONFIDENTIAL -- the source is marked confidential by Global "
    "Garden (Barry's active supplier for everything except Bionova). Costs, "
    "terms and this list NEVER appear in anything outbound; margins as "
    "percentages may be discussed with Barry only.\n\n"
    "HOW TO READ: rows are `[Item Code][Description] [Case Qty] [Wholesale each] "
    "[SRP]`. SRP is the supplier's suggested retail. Margin at SRP = (SRP - "
    "wholesale) / SRP, typically 40-45% on this list -- BUT the SRP proved "
    "FICTION for Emerald Harvest online (real market ~50-60% of SRP), and GG's "
    "own PUBLIC site retails some items at or below the wholesale it bills "
    "Barry. Never price to SRP without a live web check. Before any promo or "
    "bundle on a non-Bionova product: lookup_product for the live price, find "
    "the row here, and CHECK THE MARGIN IS REAL. Bionova costs live in "
    "bionova-cost-basis, not here. Source PDF: "
    "data/bionova-evidence/global-garden-wholesale-2025-09-30.pdf. "
    "Item codes GG-xxxxxx match store SKUs where set. Verify any odd number "
    "against the PDF.\n"
)


def family_key(marker: str) -> str:
    m = marker.strip()
    for pfx in ("EMERALD HARVEST", "DIMLUX", "CULTIWOOL", "BIONOVA",
                "GROWER'S ALLY", "THE AMAZING DOCTOR ZYMES", "GREEN HOUSE FEEDING",
                "CLOSEOUT ITEMS", "SOLD IN CASE"):
        if m.startswith(pfx):
            return pfx
    return m.split(" - ")[0]


def split_sections(lines: list[str]) -> list[tuple[str, list[str]]]:
    """[(marker, lines-including-marker)] -- text before the first marker is
    attached to the first section so nothing is dropped."""
    idx = [i for i, l in enumerate(lines) if MARKER_RE.match(l)]
    if not idx:
        return [("(all)", lines)]
    out = []
    lead = lines[:idx[0]]
    for n, i in enumerate(idx):
        j = idx[n + 1] if n + 1 < len(idx) else len(lines)
        body = lines[i:j]
        if n == 0 and lead:
            body = lead + body
        out.append((lines[i].strip(), body))
    return out


def pack(sections):
    """Greedy: whole families stay together unless one family alone is over."""
    fams = []
    for marker, body in sections:
        k = family_key(marker)
        if fams and fams[-1][0] == k:
            fams[-1][1].append((marker, body))
        else:
            fams.append([k, [(marker, body)]])
    parts, cur, cur_n = [], [], 0
    for k, secs in fams:
        n = sum(len("\n".join(b)) + 1 for _, b in secs)
        if cur and cur_n + n > PART_BODY_MAX:
            parts.append(cur)
            cur, cur_n = [], 0
        if n > PART_BODY_MAX:
            # one family too big on its own -- split it by section
            for m, b in secs:
                sn = len("\n".join(b)) + 1
                if cur and cur_n + sn > PART_BODY_MAX:
                    parts.append(cur)
                    cur, cur_n = [], 0
                cur.append((k, [(m, b)]))
                cur_n += sn
            continue
        cur.append((k, secs))
        cur_n += n
    if cur:
        parts.append(cur)
    return parts


def build_part(n: int, total: int, fams, all_names: list[str]) -> tuple[str, str]:
    names = [k.title().replace("'S", "'s") for k, _ in fams]
    markers = [m.title() for _, secs in fams for m, _ in secs]
    brand_words = sorted({w.lower() for m in markers for w in re.findall(r"[A-Za-z][A-Za-z'\-]{2,}", m)}
                         - {"and", "the", "by", "items", "only", "sold", "case", "qtys",
                            "available", "while", "supplies", "last", "line"})
    body = "\n".join("\n".join(b) for _, secs in fams for _, b in secs).strip()
    title = f"Global Garden wholesale price list (2025-09-30) -- part {n} of {total}: {', '.join(names)}"
    others = [x for i, x in enumerate(all_names, 1) if i != n]
    # THE ROUTING LINE IS READ TO 1,200 CHARS AND NOT ONE MORE (memory.
    # _skill_use_when, measured 2026-09-17: part 3's brand list ran past the
    # cap and its generic words -- cost, margin, wholesale -- fell off the
    # end, so a plain cost question could not make it eligible). Order:
    # the short core every part needs, then the brands (eligibility on a
    # named product), then the long generic tail, cut at a comma under cap.
    core = "wholesale cost, cost, margin, margins, srp, price list, global garden"
    tail = ", ".join(w for w in GENERIC_USE_WHEN.split(", ") if w not in core)
    use_when = f"USE WHEN: {core}, {', '.join(brand_words)}, {tail}"
    if len(use_when) > 1150:
        use_when = use_when[:1150].rsplit(",", 1)[0]
    # The `#` heading sits INSIDE the 1,200-char head window the routing
    # reader scans (memory._skill_use_when reads content[:1200]), and add_fact
    # prepends a TITLE line on top of it. A long heading listing every family
    # cost part 3 the last 209 chars of its routing line. Heading kept short;
    # the family list rides on its own line AFTER the routing line.
    text = (
        f"# Global Garden wholesale price list -- part {n} of {total}\n\n"
        f"{use_when}.\n\n"
        f"Covers: {', '.join(names)} (list of 2025-09-30).\n\n"
        f"{HOW_TO_READ}\n"
        f"This is part {n} of {total}. The other parts cover: "
        + "; ".join(f"part {i}: {x}" for i, x in enumerate(all_names, 1) if i != n)
        + ".\n\n---\n\n" + body + "\n"
    )
    return f"global-garden-wholesale-pricelist-part{n}.md", text


def main() -> None:
    apply = "--apply" in sys.argv
    with memory.get_db() as conn:
        row = conn.execute(
            "SELECT id, content FROM facts WHERE category=? AND source_name=? AND status='active'",
            (CATEGORY, SOURCE)).fetchone()
    if not row:
        # Already chunked: rebuild from the backup taken on the first apply so
        # a routing-line fix can be re-applied without the source row.
        import glob
        backups = sorted(glob.glob(os.path.join(ROOT, "data", "backup_fact*_gg_pricelist_*.md")))
        if not backups:
            print("source fact not active and no backup found -- nothing to do")
            return
        with open(backups[-1], encoding="utf-8") as fh:
            content = fh.read()
        row = {"id": os.path.basename(backups[-1]).split("_")[1].lstrip("fact")}
        print(f"source row already superseded; rebuilding from {os.path.basename(backups[-1])}")
    else:
        content = row["content"]
    lines = content.splitlines()
    try:
        cut = lines.index("---")
    except ValueError:
        cut = 0
    sections = split_sections(lines[cut + 1:])
    parts = pack(sections)
    names = [", ".join(k.title() for k, _ in p) for p in parts]
    built = [build_part(i, len(parts), p, names) for i, p in enumerate(parts, 1)]

    print(f"source fact {row['id']}: {len(content):,} chars, {len(sections)} sections -> {len(parts)} parts")
    for fn, text in built:
        assert len(text) <= 18_500, f"{fn} is {len(text)} chars -- over the ceiling"
        print(f"  {fn:<48} {len(text):>6} chars")
    # Every data row must survive the split, byte for byte.
    src_rows = [l for l in lines[cut + 1:] if l.strip()]
    out_rows = [l for _, t in built for l in t.split("---\n\n", 1)[1].splitlines() if l.strip()]
    missing = [l for l in src_rows if l not in out_rows]
    assert not missing, f"{len(missing)} source rows missing from the parts: {missing[:3]}"
    print(f"row check: all {len(src_rows)} source rows present in the parts")
    if not apply:
        print("\ndry run. Re-run with --apply to supersede the source and seed the parts.")
        return

    stamp = datetime.date.today().isoformat()
    bdir = os.path.join(ROOT, "data")
    bpath = os.path.join(bdir, f"backup_fact{row['id']}_gg_pricelist_{stamp}.md")
    with open(bpath, "w", encoding="utf-8") as fh:
        fh.write(content)
    outdir = os.path.join(ROOT, "knowledge", "bdubb-products", "gg-pricelist")
    os.makedirs(outdir, exist_ok=True)
    for fn, text in built:
        with open(os.path.join(outdir, fn), "w", encoding="utf-8") as fh:
            fh.write(text)
    with memory.get_db() as conn:
        for fn, _ in built:
            for r in conn.execute("SELECT id FROM facts WHERE category=? AND source_name=? AND status='active'",
                                  (CATEGORY, fn)):
                conn.execute("UPDATE facts SET status='superseded' WHERE id=?", (r["id"],))
        conn.execute("UPDATE facts SET status='superseded' WHERE id=?", (row["id"],))
    for fn, text in built:
        memory.add_fact(CATEGORY, text, fn, title=text.splitlines()[0].lstrip("# ")[:120])
    print(f"\napplied: fact {row['id']} superseded (backup {bpath}); {len(built)} parts seeded to {CATEGORY}; "
          f"files in {outdir}")
    # WHOLE LINE READABLE, not merely present -- the check that would have
    # caught the cut on the first apply.
    with memory.get_db() as conn:
        for fn, text in built:
            r = conn.execute("SELECT * FROM facts WHERE category=? AND source_name=? AND status='active'",
                             (CATEGORY, fn)).fetchone()
            full = next(l for l in text.splitlines() if l.startswith("USE WHEN:"))[len("USE WHEN: "):]
            read = memory._skill_use_when(dict(r), 1200)
            cut = len(full.rstrip(".")) - len(read)
            print(f"  {fn:<48} {'whole routing line read' if cut <= 0 else 'ROUTING LINE CUT BY ' + str(cut) + ' CHARS'}")
            assert cut <= 0, f"{fn}: routing line cut by {cut} chars -- shorten the heading or the line"


if __name__ == "__main__":
    main()
