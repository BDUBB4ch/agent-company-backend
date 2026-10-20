"""VOR'SHARA CORRECTION -- Barry, 2026-08-26, verbatim:
"Vor'Shara doesnt hate B Dubb she just dont like that hes here. She knows
humans but B Dubb doesnt know humans are in outter space yet. and he doesnt
know what Lady Vor'Shara vell is stern to and about him. But they will talk
later"

This corrects Claude's parse of the earlier five-voice message, which had
applied "hateful towards b dubb" to BOTH Vor'Shara and Keth. Barry's
correction: hers is not hatred -- she doesn't like that he's HERE, and she is
STERN to and about him. Keth's block is untouched (not corrected).

It also lands STORY canon, recorded with the voice ruling because it drives
how her lines to him play:
- She KNOWS humans. B Dubb does NOT yet know humans are in outer space.
- He does not know what Lady Vor'Shara Vel is.
- "they will talk later" -- a future conversation between them is a planned
  beat. Nobody stages it early; Barry writes it when the story arrives.

Re-runnable; asserts, backs up, syncs fact 592 byte-identical.
"""
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DISK = ROOT / "data" / "barry-character-canon.md"
DB = ROOT / "data" / "brain.db"
FACT_ID = 592

OLD_BLOCK = '''@VORSHARA -- DIRECTED 2026-08-20, EXPANDED 2026-08-26.
  2026-08-20: "i want this voice to sound more gritty and vengefull, for lady
  vor and a lil deeper."
  2026-08-26: "not slow but deliberate, slightly fast when angered or annoyed"
  + (shared with Keth) "carful and but hateful, towards b dubb for now"
  The hatred toward @B-DUBB-new is story-current ("for now").
---------------------------------------------------------------
  LOCK TEXT (paste verbatim into the prompt):
    feminine; gritty, vengeful, a little deeper; deliberate, never slow, quickening slightly when angered; careful delivery, open hatred when speaking to B Dubb
'''

NEW_BLOCK = '''@VORSHARA -- DIRECTED 2026-08-20, EXPANDED 2026-08-26, CORRECTED SAME DAY.
  2026-08-20: "i want this voice to sound more gritty and vengefull, for lady
  vor and a lil deeper."
  2026-08-26: "not slow but deliberate, slightly fast when angered or annoyed"
  2026-08-26 CORRECTION (supersedes the "hateful" read of the same day's
  message -- that word belongs to Keth, not her): "Vor'Shara doesnt hate B
  Dubb she just dont like that hes here. She knows humans but B Dubb doesnt
  know humans are in outter space yet. and he doesnt know what Lady Vor'Shara
  vell is stern to and about him. But they will talk later"
  STORY CANON THAT RIDES WITH THIS RULING, because it drives her delivery:
  * She KNOWS humans. B Dubb does NOT yet know humans are in outer space.
  * He does not know what Lady Vor'Shara Vel is.
  * A conversation between them is a PLANNED FUTURE BEAT ("they will talk
    later") -- Barry writes it when the story arrives; nobody stages it early.
  So her register toward him is STERN -- to him and about him -- not hate.
  She dislikes his presence, from a position of knowledge he doesn't share.
---------------------------------------------------------------
  LOCK TEXT (paste verbatim into the prompt):
    feminine; gritty, vengeful, a little deeper; deliberate, never slow, quickening slightly when angered; stern to and about B Dubb
'''

text = DISK.read_text(encoding="utf-8")
if NEW_BLOCK in text:
    print("already applied -- verifying sync only")
else:
    if OLD_BLOCK not in text:
        sys.exit("REFUSING: Vor'Shara block not byte-identical to expected. Check by hand.")
    shutil.copy2(DISK, ROOT / "data" / "backup_disk_canon_before_vorshara_stern_2026-08-26.md")
    text = text.replace(OLD_BLOCK, NEW_BLOCK, 1)
    DISK.write_text(text, encoding="utf-8")
    print(f"disk canon updated ({len(text):,} chars)")

con = sqlite3.connect(DB)
disk_now = DISK.read_text(encoding="utf-8")
con.execute("UPDATE facts SET content=? WHERE id=?", (disk_now, FACT_ID))
con.commit()
after = con.execute("SELECT content FROM facts WHERE id=?", (FACT_ID,)).fetchone()[0]
assert after == disk_now, "fact 592 drifted from disk"
assert "stern to and about B Dubb" in after
assert "open hatred when speaking to B Dubb" in after, \
    "Keth's hatred line should still exist (his was not corrected)"
assert after.count("open hatred when speaking to B Dubb") == 1, \
    "exactly one hatred lock should remain (Keth's)"
print(f"fact {FACT_ID} synced byte-identical at {len(after):,} chars")
print("VERIFIED: Vor'Shara stern, Keth's hatred untouched, story canon recorded")
