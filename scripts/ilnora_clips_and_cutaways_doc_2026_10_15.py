"""2026-10-15: her toolkit (fact 4919) said every moving clip is 5 seconds and had no cutaway. The builder now takes a
clip length (2-5 s, or the line decides) and a cutaway list on her on-camera parts. Replace the old wording with how it
works now; add the talk_with tool. Backs up the brain; each replacement must match once."""
import shutil
import sqlite3
import sys
from datetime import datetime

DB = "data/brain.db"
FID = 4919
EDITS = [
    ("A talking part is built in pieces of about 10 seconds, so long speeches become jump cuts -- I talk 10-20 seconds, "
     "cut away, come back.",
     "A talking part is built in pieces of about 10 seconds, so long speeches become jump cuts -- I talk 10-20 seconds, "
     "cut away, come back. **cutaway** -> on a \"me\" part, a list of pictures to cut to while I keep talking: I stay "
     "on camera for my first sentence, and my next sentences play over those pictures, in order (Barry, October 15, "
     "2026: \"she doesnt have to be on screen her whole time shes talking\"). It is also far cheaper than talking on "
     "camera."),
    ("that picture becomes a 5-second moving clip.",
     "that picture becomes a moving clip of 2 to 5 seconds -- **seconds** sets it; leave it out and the length of my "
     "line decides (a short line gets a short clip, so nothing is slowed down and looped under my voice). Barry, "
     "October 15, 2026: \"random clips length, 3-5 seconds not a fixed number, some can be 2 seconds.\""),
]
TALK = ("\n\n### Talking with my teammates -- talk_with\n"
        "talk_with starts a LIVE conversation with one or more teammates -- we talk back and forth until it is settled, "
        "any time of day. It is my choice when I want to talk something through (or when Barry asks me to). \"work\" "
        "is at the office with my tools; \"personal\" is off the clock. Barry can watch and jump in, and we all "
        "remember it afterwards.")

con = sqlite3.connect(DB)
t = con.execute("SELECT content FROM facts WHERE id=? AND status='active'", (FID,)).fetchone()
if not t or any(t[0].count(old) != 1 for old, _ in EDITS):
    sys.exit("expected text not found exactly once -- nothing changed")
con.close()
bak = f"data/brain_backup_before_clips_cutaways_{datetime.now():%Y-%m-%d_%H%M}.db"
shutil.copy2(DB, bak)
print("backup:", bak)
new = t[0]
for old, rep in EDITS:
    new = new.replace(old, rep, 1)
if "### Talking with my teammates" not in new:
    new = new.rstrip() + TALK
con = sqlite3.connect(DB)
with con:
    con.execute("UPDATE facts SET content=? WHERE id=?", (new, FID))
con.close()
print("updated", FID)
