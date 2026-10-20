"""2026-10-14: her toolkit (fact 4919) said a plant in her hands comes out generic and her non-plant-opening scenes
are painted without knowing the plant. reel_builder now draws both with a real photo of the species as a reference
(_plant_ref). Replace those two sentences with how it works now. Backs up the brain; each must match once."""
import shutil
import sqlite3
import sys
from datetime import datetime

DB = "data/brain.db"
FID = 4919
EDITS = [
    ("The picture of me is drawn from my face and body and my words only -- it does not know any plant species, so a "
     "plant in my hands comes out as a generic flower; my hands work with things the engine knows (a mortar, a jar, a "
     "knife, a book, a lantern) and the plant gets its own picture.",
     "The picture of me is drawn from my face and body and my words. When my \"me\" part also carries a **plant**, a "
     "real photo of that species goes in as a reference, so the plant in my hands or beside me is the real plant (not "
     "when my shot names one of Barry's store products -- the product takes that place)."),
    ("When my picture opens on anything else (a ruin, a workbench, a bowl), it is PAINTED from my words by the picture "
     "engine, and the engine often does not know what a rare plant looks like -- so for the plant itself I open on the "
     "plant.",
     "When my picture opens on anything else (a sick man, a healer grinding the root, a ruin, a bowl), it is drawn from "
     "my words with a real photo of that species as a reference, so the plant in the action is the real plant (if no "
     "photo of it can be found, it is painted from my words alone)."),
]

con = sqlite3.connect(DB)
t = con.execute("SELECT content FROM facts WHERE id=? AND status='active'", (FID,)).fetchone()
if not t or any(t[0].count(old) != 1 for old, _ in EDITS):
    sys.exit("expected text not found exactly once -- nothing changed")
con.close()
bak = f"data/brain_backup_before_plant_reference_{datetime.now():%Y-%m-%d_%H%M}.db"
shutil.copy2(DB, bak)
print("backup:", bak)
new = t[0]
for old, rep in EDITS:
    new = new.replace(old, rep, 1)
con = sqlite3.connect(DB)
with con:
    con.execute("UPDATE facts SET content=? WHERE id=?", (new, FID))
con.close()
print("updated", FID)
