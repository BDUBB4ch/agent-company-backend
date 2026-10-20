"""2026-10-17: Barry's own description of Taliyah, added to personalities/Taliyah.md word for word under his name.
Backs up the file first; appends only (nothing in the file is changed)."""
import os
import shutil
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import ingest  # noqa: E402

BARRY = ("i said Taliyah is a super smart girl from the hood, MIT smart,  World knowledge smart. Politics etc. she knows "
         "street shit, like gangs and cops, drugs etc. Shes just as smart if not smarter than Sophie. They met in School and "
         "have been friends ever since.  She just knows things. She also know languages and is an excellent teacher of "
         "languages. spanish, russian, chinese, arabic and ancient American Languages. She is indigenous American Like me, "
         "I'm blackfoot. from south Carolina. My ancestor ruled this whole place, i was born with 6 fingers on each hand like "
         "my people has. Taliyah can choose her own or be the same as me. They call us black or africanamerican, but we are "
         "the true Americans, Copper colored greatness!")

path = ingest._personality_path("Taliyah") if hasattr(ingest, "_personality_path") else os.path.join(ROOT, "personalities", "Taliyah.md")
before = ingest.personality_of("Taliyah") or ""
if "MIT smart" in before:
    sys.exit("already there -- nothing changed")
bak = os.path.join(ROOT, "data", f"backup_personality_Taliyah_{datetime.now():%Y-%m-%d_%H%M}.md")
shutil.copy2(path, bak)
ingest.set_personality("Taliyah", before.rstrip() + "\n\nBarry, 2026-10-17:\n\"" + BARRY + "\"\n")
after = ingest.personality_of("Taliyah")
assert after.startswith(before.rstrip()), "existing text changed -- check the backup"
print("backup:", bak)
print(len(before), "->", len(after), "chars")
