"""Barry 2026-10-14: remove the "no other people in my videos" rule from Ilnora's active work docs and put his new
words in its place. Mind-/worknote- facts untouched. Backs up the brain first; every replacement must match once."""
import shutil
import sqlite3
import sys
from datetime import datetime

DB = "data/brain.db"
NEW_Q = ('"we need other people and animals etc, in order for [{who}] to create movie like vids" and "these videos '
         'needs to be movie like. we need good stuff, like if the plant gives boils, show a sick person. get gritty. '
         'Show the good stuff, you know what i mean?"')

EDITS = {
    4702: ('- **No other people on screen.** Barry: "i dont want any other people in my videos" -- you are the only '
           'person in your videos; every other picture is the plants, the work and the places, with no one else in it.',
           "- Barry, 2026-10-14: " + NEW_Q.format(who="you")),
    4904: ('- **Story without other people.** Barry: "i dont want any other people in my videos" -- you are the only '
           'person on screen. Tell the human history through what people leave behind: an abandoned battlefield at '
           "dawn with the plant growing through rusted armour; a ruined temple; an apothecary shelf with one bottle "
           "missing; an empty throne; a ship's hold full of sacks; a candle-lit desk with an open herbal; a field after "
           "a storm. Places, objects, light, weather and the plant itself carry it.",
           "- Barry, 2026-10-14: " + NEW_Q.format(who="you")),
    4918: ('- "i dont want any other people in my videos" -- I am the only person on screen.',
           "- " + NEW_Q.format(who="me") + " (Barry, Wednesday October 14, 2026)"),
    4919: ("One clear scene, the single most dramatic thing in the line. No other people in it (Barry's rule), no "
           "writing in it.",
           "One clear scene, the single most dramatic thing in the line. No writing in it."),
    4972: (" Story without other people: fire circle with ash, mortar with ground root, gourd, vial of seeds.", ""),
}

con = sqlite3.connect(DB)
rows = {}
for fid, (old, _new) in EDITS.items():
    r = con.execute("SELECT content, status FROM facts WHERE id=?", (fid,)).fetchone()
    if not r or r[1] != "active" or r[0].count(old) != 1:
        sys.exit(f"fact {fid}: expected text not found exactly once (status={r and r[1]}) -- nothing changed")
    rows[fid] = r[0]
con.close()

bak = f"data/brain_backup_before_people_allowed_{datetime.now():%Y-%m-%d_%H%M}.db"
shutil.copy2(DB, bak)
print("backup:", bak)

con = sqlite3.connect(DB)
with con:
    for fid, (old, new) in EDITS.items():
        con.execute("UPDATE facts SET content=? WHERE id=?", (rows[fid].replace(old, new, 1), fid))
        print("updated", fid)
con.close()
