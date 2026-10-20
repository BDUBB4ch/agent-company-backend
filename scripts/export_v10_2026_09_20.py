"""Export the live V10 script exactly as Elliot has it.

Strips only the `_SEP` rule lines the office inserts to find block boundaries --
those are machinery, not Barry's writing. Verifies the exported text matches the
copy in his Downloads so the two can never quietly drift.
"""
import glob
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import script_wip  # noqa: E402

MD = r"C:\Users\Owner\Downloads\TALIA_CREW_EP1_V10_RENUMBERED.md"
DEST = r"C:\Users\Owner\Desktop\TALIA_CREW_EP1_V10_2026-09-20.md"

cands = glob.glob(os.path.join(ROOT, "data", "*.db"))
db = [c for c in cands if "brain" in os.path.basename(c)] or cands
cur = sqlite3.connect(db[0]).cursor()
cur.execute("select id, content from facts where source_name=? and status='active'",
            (script_wip.WIP_SOURCE,))
fid, stored = cur.fetchone()

clean = "\n".join(l for l in stored.split("\n") if l != script_wip._SEP)
open(DEST, "w", encoding="utf-8").write(clean)

print(f"fact {fid}: {len(stored):,} chars stored ({len(clean):,} without separators)")
print(f"exported -> {DEST}")

if os.path.exists(MD):
    md = open(MD, encoding="utf-8").read()
    if md == clean:
        print(f"\nDownloads copy is IDENTICAL -- both in step ({len(md):,} chars)")
    else:
        print(f"\n⚠️ Downloads copy DIFFERS: {len(md):,} vs {len(clean):,} chars")
        a, b = md.split("\n"), clean.split("\n")
        for i in range(min(len(a), len(b))):
            if a[i] != b[i]:
                print(f"  first difference at line {i+1}")
                print(f"    downloads: {a[i][:110]}")
                print(f"    live     : {b[i][:110]}")
                break
