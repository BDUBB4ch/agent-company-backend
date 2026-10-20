"""Throwaway: confirm test turns did not land in Elliot's real thread."""
import glob
import os
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cands = glob.glob(os.path.join(ROOT, "data", "*.db"))
db = [c for c in cands if "brain" in os.path.basename(c)] or cands
con = sqlite3.connect(db[0])
cur = con.cursor()
cur.execute("select count(*) from conversations where agent_id='movie'")
print("movie thread turns:", cur.fetchone()[0])
cur.execute("select role, substr(content,1,60) from conversations where agent_id='movie' order by id desc limit 2")
for role, content in cur.fetchall():
    print(" ", role, "|", content.replace("\n", " "))
