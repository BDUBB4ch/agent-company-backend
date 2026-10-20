"""Barry 2026-10-14: "longs i want at least 8 minutes, if she cant handle that ot the ltx or comfy cand do that long
then do 7 minutes". The Oct 11 any-length rule now holds for Shorts only: scope it, and put his Long words in every
active doc that said a Long is any length. Backs up the brain; every replacement must match exactly once."""
import shutil
import sqlite3
import sys
from datetime import datetime

DB = "data/brain.db"
Q = ('"longs i want at least 8 minutes, if {she} cant handle that ot the ltx or comfy cand do that long then do 7 '
     'minutes"')
EDITS = [
    (4702,
     'A Short is vertical, a Long is widescreen; the story decides how long it runs. (You speak about 2.3 words a '
     'second including pauses.)',
     'A Short is vertical, a Long is widescreen; the story decides how long a Short runs. A Long is at least 8 '
     'minutes: ' + Q.format(she="[you]") + ' (Barry, Wednesday October 14, 2026) -- about 1500 words, never under '
     '1310. (You speak about 2.3 words a second in a Short and about 3.1 in a Long, pauses included -- measured on '
     'your built videos.)'),
    (4904, '### A Long (widescreen, any length)', '### A Long (widescreen, at least 8 minutes)'),
    (4918,
     '- Any length: "i dont care how long or short, she does them.',
     '- Shorts, any length: "i dont care how long or short, she does them.'),
    (4918,
     'show that stuff with good visuals." (Barry, Wednesday October 14, 2026)',
     'show that stuff with good visuals." (Barry, Wednesday October 14, 2026)\n- Longs: ' + Q.format(she="[I]")
     + ' (Barry, Wednesday October 14, 2026)'),
    (4919,
     'Any length -- the story decides (Barry, October 11, 2026).',
     'A Short is any length -- the story decides (Barry, October 11, 2026). A Long is at least 8 minutes, 7 at the '
     'very least (Barry, October 14, 2026).'),
    (5029,
     'Keep going until the story is told -- any length (Barry, October 11, 2026).',
     'Keep going until the story is told -- a Long at least 8 minutes, 7 at the very least (Barry, October 14, '
     '2026).'),
]

con = sqlite3.connect(DB)
docs = {}
for fid, old, _new in EDITS:
    if fid not in docs:
        r = con.execute("SELECT content FROM facts WHERE id=? AND status='active'", (fid,)).fetchone()
        if not r:
            sys.exit(f"fact {fid} not active -- nothing changed")
        docs[fid] = r[0]
    if docs[fid].count(old) != 1:
        sys.exit(f"fact {fid}: expected text not found exactly once: {old[:60]} -- nothing changed")
con.close()
bak = f"data/brain_backup_before_long_length_{datetime.now():%Y-%m-%d_%H%M}.db"
shutil.copy2(DB, bak)
print("backup:", bak)
for fid, old, new in EDITS:
    docs[fid] = docs[fid].replace(old, new, 1)
con = sqlite3.connect(DB)
with con:
    for fid, text in docs.items():
        con.execute("UPDATE facts SET content=? WHERE id=?", (text, fid))
        print("updated", fid)
con.close()
