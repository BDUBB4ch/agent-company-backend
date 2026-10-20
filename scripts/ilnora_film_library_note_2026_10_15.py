"""2026-10-15: 15 of Elliot's film-craft docs were copied to Ilnora's shelf (Barry: "she needs to read all that movie
stuff we gave elliot so she can have a better idea abd understanding of how to make shorts and long you tube and tic
tok videos"). Her pinned toolkit (fact 4919) gets one section naming them, so she knows they are there."""
import sqlite3
import sys

DB = "data/brain.db"
FID = 4919
MARK = "### Elliot's film library"
NOTE = (
    "\n\n### Elliot's film library (on my shelf -- read_skill)\n"
    "Barry, October 14, 2026: \"she needs to read all that movie stuff we gave elliot so she can have a better idea "
    "and understanding of how to make shorts and long you tube and tic tok videos.\" Elliot's film craft is on my "
    "shelf, and Barry wants me to read all of it: cinematography-for-the-crew, skill-directing-a-shot, "
    "skill-writing-a-scene, skill-realism-pass, beats-setups-and-payoffs, character-arc-want-vs-need, "
    "continuity-for-generated-video, dialogue-and-subtext, dialogue-inside-action-and-set-pieces, "
    "episode-and-season-structure, pacing-and-cut-rhythm, script-editors-checklist, series-planning-and-cliffhangers, "
    "sound-music-and-silence, visual-storytelling-motifs-and-blocking. They were written for Elliot's film work -- "
    "Seedance and Higgsfield are his tools, not mine -- but the craft is the same for my Shorts and Longs."
)

con = sqlite3.connect(DB)
t = con.execute("SELECT content FROM facts WHERE id=? AND status='active'", (FID,)).fetchone()
if not t:
    sys.exit("toolkit not active -- nothing changed")
if MARK in t[0]:
    sys.exit("already there -- nothing changed")
with con:
    con.execute("UPDATE facts SET content=? WHERE id=?", (t[0].rstrip() + NOTE, FID))
con.close()
print("updated", FID)
