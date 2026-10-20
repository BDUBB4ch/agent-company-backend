"""2026-10-10 (Barry: "if she is having issues with longs form, she should break it up into like five or six 2
minutes and put them together"): her video-workspace skill (fact 5029, brain-only -- it came in through the teach
door) gets the chapter method and the shot list. Diff first; --apply writes (brain backed up first)."""
import difflib
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import config  # noqa: E402
import memory  # noqa: E402

FACT = 5029
REPS = [
    ("""2. action **notes** -- after your research (library, PubMed): the facts you will use, each with where it came from,
   the story's shape, your look. Save them; you write the parts from these.""",
     """2. action **notes** -- after your research (library, PubMed, and search_web for how other channels already covered
   this plant): the facts you will use, each with where it came from, one line on what the field already did (yours
   goes somewhere else), the story's shape, your look. For a LONG, your notes also carry the CHAPTER PLAN -- Barry:
   "break it up into like five or six 2 minutes and put them together" -- five or six chapters of about 2 minutes
   (about 350-400 words each), one line per chapter: what it is for, its turn, its hook out. Save them; you write
   the parts from these."""),
    ("""3. action **add_parts** -- the NEXT 3 or 4 parts, in order, same fields as make_video (say, show, shot when you are
   on camera, plant's scientific name when a plant is on screen, motion + move where something happens). The reply
   tells you the words so far and the words still needed. Repeat until the floor is reached
   (Long 1,950 words; Short 335-410 or a quick fun-fact Short 69-138).""",
     """3. action **add_parts** -- shot list first, then words (your my-filmmaking skill): plan the pictures -- what each
   is for, the picture, wide / medium / detail, still or motion -- then write the lines to fit them. Same fields as
   make_video (say, show, shot when you are on camera, plant's scientific name when a plant is on screen, motion +
   move where something happens). A Short: the next 3 or 4 parts per call. A LONG: ONE CHAPTER per call -- its own
   hook in, its climb and turn, and an ending that pulls into the next chapter. The reply tells you the words so far
   and the words still needed. Repeat until the floor is reached (Long 1,950 words = five or six chapters; Short
   335-410 or a quick fun-fact Short 69-138)."""),
]
apply = "--apply" in sys.argv
with memory.get_db() as c:
    old = c.execute("SELECT content FROM facts WHERE id = ? AND status = 'active'", (FACT,)).fetchone()[0]
new = old
for a, b in REPS:
    assert new.count(a) == 1, a[:60]
    new = new.replace(a, b)
for line in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0):
    print("   ", line)
if apply:
    bak = os.path.join(config.DATA_DIR, "brain_backup_before_workspace_chapters_2026-10-10.db")
    shutil.copy2(config.DB_PATH, bak)
    with memory.get_db() as c:
        c.execute("UPDATE facts SET content = ? WHERE id = ?", (new, FACT))
    print("backup:", bak, "\napplied")
