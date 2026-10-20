"""V9A -> V9A.1. Barry, 2026-09-07: "we only need to add the fights to our V9A
and call it V9A.1" -- from Betty's EXTENDED FIGHTS doc, ONLY:
  * SHOT 08B  -- NEW: the B Dubb corridor fight, inserted after SHOT 08A
  * SHOT 09A  -- REPLACED by her 2:00 breach, which absorbs 10A and 11A
                 (those two blocks are removed; archived in the backup)
  * SHOT 13A  -- REPLACED by her 45-second lab corridor
Everything else in V9A is untouched. Her text is carried as she wrote it
(converted to V9A's block shape in data/v9a_extended_fights_2026-09-07.md),
with only the standing substitutions outside quoted speech.

The working copy is written directly (save_block caps a block at 6,000 chars
and appends new labels at the END; 09A is ~8K and 08B belongs after 08A).
Same backup, same ledger regeneration. Then the script, its file, the ledger
and the plumbing names become V9A.1. One-shot: refuses to run twice.
"""
import re
import sys
import pathlib
import importlib

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))
import memory                  # noqa: E402
import script_wip as sw        # noqa: E402

OLD, NEW = "v9A", "v9A.1"
STAGED = REPO / "data" / "v9a_extended_fights_2026-09-07.md"
FILE_OLD = pathlib.Path("C:/Users/Owner/Downloads/TALIA_CREW_EP1_PRODUCTION_V9A.md")
FILE_NEW = pathlib.Path("C:/Users/Owner/Downloads/TALIA_CREW_EP1_PRODUCTION_V9A.1.md")
LOC = "@loc_hidden-black-site"
QUOTED = re.compile(r'"[^"\n]*"')


def subst(seg):
    seg = re.sub(r"\bB DUBB\b", "@b-dubb", seg)
    seg = re.sub(r"@Bia\b(?!-)(?!'s-Pistol)", "@Bia-2", seg)
    seg = re.sub(r"@yannah\b", "@Yannah", seg)
    seg = re.sub(r"@Keth\b", "@keth", seg)
    seg = re.sub(r"(?<![@\w-])Bia(?=['\s.,;:!?)]|$)", "@Bia-2", seg)
    seg = re.sub(r"(?<![@\w-])Yannah(?=['\s.,;:!?)]|$)", "@Yannah", seg)
    seg = re.sub(r"(?<![@\w-])Tazz(?=['\s.,;:!?)]|$)", "@Tazz", seg)
    seg = re.sub(r"(?<![@\w-])Keth(?=['\s.,;:!?)]|$)", "@keth", seg)
    seg = seg.replace("Silenced alien pistols", "@Bia's-Pistol* and @Yannah's-Machine-Pistol, silenced")
    seg = re.sub(r"\bGlock\b", "@B-Dubb's-Banger", seg)
    seg = re.sub(r"\b(?:military\s+)?black[\s-]site\b", LOC, seg, flags=re.I)
    seg = re.sub(r"\bfacility('s)?\b", lambda m: LOC + (m.group(1) or ""), seg, flags=re.I)
    return seg.replace(f"Gray {LOC} jumpsuit", "Gray facility jumpsuit")


def fix_line(line):
    pos, out = 0, []
    for m in QUOTED.finditer(line):
        out.append(subst(line[pos:m.start()])); out.append(m.group(0)); pos = m.end()
    out.append(subst(line[pos:]))
    return "".join(out)


def patch(path, pairs):
    p = pathlib.Path(path); t = p.read_text(encoding="utf-8")
    for old, new, n in pairs:
        c = t.count(old); assert c == n, f"{path}: expected {n} of {old[:60]!r}, found {c}"
        t = t.replace(old, new)
    tmp = p.with_suffix(p.suffix + ".tmp"); tmp.write_text(t, encoding="utf-8"); tmp.replace(p)


# ---- 0. guards + backup (old module state, old names) ----
fact = sw._get_wip_fact()
assert fact and sw.WIP_SOURCE == f"ep1-production-{OLD}-WIP.md", "expected the V9A working copy"
assert "SHOT 08B" not in fact["content"], "already extended -- refusing to run twice"
sw._backup("extend-fights-to-V9A.1", "08B-09A-13A")
header, blocks = sw._split_blocks(fact["content"])
labels = [sw._block_label(b) for b in blocks]

# ---- 1. the three staged blocks, substitutions applied outside quotes ----
staged = [s.strip() for s in STAGED.read_text(encoding="utf-8").split("=====BLOCK=====")]
staged = ["\n".join(fix_line(l) for l in s.splitlines()) for s in staged]
new = {sw._block_label(s): s for s in staged}
assert set(new) == {"SHOT 8B", "SHOT 9A", "SHOT 13A"}, set(new)

# ---- 2. splice: replace 9A and 13A, remove 10A/11A, insert 8B after 8A ----
out = []
for b, l in zip(blocks, labels):
    if l in ("SHOT 10A", "SHOT 11A"):
        continue                       # absorbed into the new 09A (archived in the backup)
    if l in ("SHOT 9A", "SHOT 13A"):
        out.append(new[l]); continue
    out.append(b)
    if l == "SHOT 8A":
        out.append(new["SHOT 8B"])
assert [sw._block_label(b) for b in out].count("SHOT 8B") == 1
assert len(out) == len(blocks) - 1, (len(out), len(blocks))

# ---- 3. header -> V9A.1 ----
assert header.count("Production Script V9A -- WORK IN PROGRESS") == 1
assert header.count("Production Script V9A — FULL 30-45 MIN VERSION") == 1
header = (header
          .replace("Production Script V9A -- WORK IN PROGRESS", "Production Script V9A.1 -- WORK IN PROGRESS")
          .replace("Production Script V9A — FULL 30-45 MIN VERSION", "Production Script V9A.1 — FULL 38-45 MIN VERSION")
          .replace('This is THE LIVE EP1 production script as of 2026-09-07 ("replace v9 with this").',
                   'This is THE LIVE EP1 production script. V9A.1 (2026-09-07) = V9A + the extended fights\n'
                   'from Betty\'s EXTENDED FIGHTS draft, on Barry\'s word: NEW SHOT 08B (B Dubb\'s corridor\n'
                   'fight), SHOT 09A now the 2:00 breach (absorbs the old 10A and 11A), SHOT 13A now the\n'
                   '45-second lab corridor. Nothing else from that draft was taken.'))

# ---- 4. rename the plumbing: code constants + the main.py ledger literal ----
patch("backend/script_wip.py", [
    (f'WIP_SOURCE = "ep1-production-{OLD}-WIP.md"', f'WIP_SOURCE = "ep1-production-{NEW}-WIP.md"', 1),
    (f'LEDGER_SOURCE = "ep1-{OLD}-live-state"', f'LEDGER_SOURCE = "ep1-{NEW}-live-state"', 1),
    (f"1. THE WIP SCRIPT (`ep1-production-{OLD}-WIP.md`", f"1. THE WIP SCRIPT (`ep1-production-{NEW}-WIP.md`", 1),
    (f"2. THE LEDGER (`ep1-{OLD}-live-state`", f"2. THE LEDGER (`ep1-{NEW}-live-state`", 1),
    ("Production Script V9A -- WORK IN PROGRESS (living document)", "Production Script V9A.1 -- WORK IN PROGRESS (living document)", 1),
    ('title="EP1 V9A production script -- WORK IN PROGRESS"', 'title="EP1 V9A.1 production script -- WORK IN PROGRESS"', 1),
    ('"EP1 V9A PRODUCTION SCRIPT -- LIVE STATE (this updates every time a "', '"EP1 V9A.1 PRODUCTION SCRIPT -- LIVE STATE (this updates every time a "', 1),
    (f"('ep1-production-{OLD}-WIP').", f"('ep1-production-{NEW}-WIP').", 1),
    ('title="EP1 V9A production script -- live state"', 'title="EP1 V9A.1 production script -- live state"', 1),
])
patch("backend/main.py", [(f'_facts.get("ep1-{OLD}-live-state", "")', f'_facts.get("ep1-{NEW}-live-state", "")', 1)])
with memory.get_db() as c:
    c.execute("UPDATE facts SET source_name=? WHERE id=? AND status='active'", (f"ep1-production-{NEW}-WIP.md", fact["id"]))
    c.execute("UPDATE facts SET source_name=? WHERE source_name=? AND status='active'", (f"ep1-{NEW}-live-state", f"ep1-{OLD}-live-state"))

# ---- 5. write the working copy under the new name (regenerates the ledger) ----
importlib.reload(sw)
assert sw.WIP_SOURCE == f"ep1-production-{NEW}-WIP.md"
sw._write_wip(header, out)

# ---- 6. the file: regenerated FROM the working copy, Betty's divider ----
wip = sw._get_wip_fact()["content"]
FILE_NEW.write_text(wip.replace(sw._SEP, "─" * 107), encoding="utf-8")
if FILE_OLD.exists():
    FILE_OLD.unlink()
for s in ("scripts/blend_v9_into_seedance_script_2026_09_07.py", "scripts/blend_v9_into_rewrite_v1_2026_09_07.py"):
    p = REPO / s; t = p.read_text(encoding="utf-8")
    if "HISTORICAL -- do not re-run" not in t:
        t = t.replace('import re\n', 'raise SystemExit("HISTORICAL -- do not re-run: V9A.1 is maintained in the WIP (script_wip), '
                      'and a re-run would regress the 2026-09-07 fight extensions.")\nimport re\n', 1)
        p.write_text(t, encoding="utf-8")

# ---- 7. verify ----
import script_index as si
hdr2, blks2 = sw._split_blocks(wip)
labs = [sw._block_label(b) for b in blks2]
print("blocks:", len(blks2), "| order around the change:", [l for l in labs if l in ("SHOT 8A", "SHOT 8B", "SHOT 9A", "SHOT 10A", "SHOT 11A", "SHOT 12A", "SHOT 13A", "SHOT 14A")])
print("scripts:", [s["title"] for s in si.list_scripts(sw.OFFICE)], "| default:", si.default_script(sw.OFFICE))
r = si.read_scene(sw.OFFICE, "SHOT 08B"); print("read_scene 08B found:", r.get("found"), "| from:", r.get("script"))
r = si.read_scene(sw.OFFICE, "SHOT 10A"); print("read_scene 10A found:", r.get("found"), "(expected False)")
led = next(f["content"] for f in memory.get_active_facts_for_agent(sw.OFFICE) if f.get("source_name") == sw.LEDGER_SOURCE)
print("ledger:", led.splitlines()[0][:50], "|", led.splitlines()[1][:60])
print("file:", FILE_NEW.name, f"{len(FILE_NEW.read_text(encoding='utf-8')):,} chars | header:", wip.splitlines()[2][:60])
