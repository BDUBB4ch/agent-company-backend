"""Does SHOT 01's source put a weapon in anyone's hand? And is the
weapon-carry rule actually reaching Elliot on a shot ask?"""
import glob
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import script_wip  # noqa: E402

cands = glob.glob(os.path.join(ROOT, "data", "*.db"))
db = [c for c in cands if "brain" in os.path.basename(c)] or cands
cur = sqlite3.connect(db[0]).cursor()
cur.execute("select content from facts where source_name=? and status='active'",
            (script_wip.WIP_SOURCE,))
text = cur.fetchone()[0]
header, blocks = script_wip._split_blocks(text)

for b in blocks:
    if script_wip._block_label(b).replace(" ", "").upper() in ("SHOT1", "SHOT01"):
        print("=== SHOT 01 SOURCE (what Elliot is handed) ===")
        print(b.strip()[:2200])
        print()
        wep = re.findall(r"(pistol|revolver|weapon|gun|banger|blaster|holster|drawn|raise[sd]?)",
                         b, re.I)
        print("weapon words in the source block:", wep or "NONE")
        break

print()
print("=== is the weapon-carry rule in the shot brief? ===")
dump = os.path.join(ROOT, "data", "_shot_directive_dump.txt")
d = open(dump, encoding="utf-8").read() if os.path.exists(dump) else ""
for probe in ("A WEAPON HANDLE ONLY WHEN THE WEAPON IS ACTUALLY IN PLAY",
              "nobody is holding one",
              "A stowed weapon is WARDROBE"):
    print(f"  {probe[:52]!r:<56} {probe in d}")

print()
print("=== is the carry ruling in the canon Elliot reads? ===")
cur.execute("select content from facts where source_name='character-anchors-card.md' "
            "and status='active'")
r = cur.fetchone()
anchors = r[0] if r else ""
cur.execute("select content from facts where source_name='barry-character-canon.md' "
            "and status='active'")
r2 = cur.fetchone()
canon = r2[0] if r2 else ""
for name, body in (("anchors card (PINNED)", anchors), ("full canon (on-demand)", canon)):
    print(f"  {name:<26} carry section present: "
          f"{'HOW THEY CARRY IT' in body}")
