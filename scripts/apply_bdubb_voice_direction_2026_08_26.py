"""B DUBB'S VOICE DIRECTION -- Barry, 2026-08-26, verbatim:
"i dont like the way my voice is generated in higgs field. he needs to dound
like an inner city black man from the south, not some white tough guy from
the movies"

WHY THE OLD LOCK FAILED: the lock text was the single word "clean", which the
canon itself records as an AUDIO-QUALITY note (his sample peaked at 0.0 dBFS),
not a character. The Voice Bible's five slots (register, range, tempo, manner,
ACCENT/ORIGIN) had accent/origin empty -- so Higgsfield filled the silence
with its default action-movie read. This ruling fills that slot.

THE PASTE LOCK IS POSITIVE-ONLY, deliberately: ONEIRIC's words-you-summon rule
(the words you write are the words you summon, including the ones inside a
"no") means "not some white tough guy from the movies" must NOT go into the
prompt -- writing it would summon it. The negative half is recorded here as
the ruling; the lock carries only his positive descriptors.

House pattern: assert anchors before writing, backup both copies, splice,
push disk -> fact 592, verify byte-identical. Re-runnable (idempotent).
"""
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DISK = ROOT / "data" / "barry-character-canon.md"
DB = ROOT / "data" / "brain.db"
FACT_ID = 592

OLD_BLOCK = '''@B-DUBB-new -- DIRECTED 2026-08-20. HIS WORDS: "B dubb voice audio should be
cleaner."
---------------------------------------------------------------
  LOCK TEXT (paste verbatim into the prompt):
    clean
'''

NEW_BLOCK = '''@B-DUBB-new -- DIRECTED 2026-08-20 AND 2026-08-26. HIS WORDS, both rulings:
2026-08-20: "B dubb voice audio should be cleaner."
2026-08-26: "i dont like the way my voice is generated in higgs field. he
needs to dound like an inner city black man from the south, not some white
tough guy from the movies"
---------------------------------------------------------------
  LOCK TEXT (paste verbatim into the prompt):
    clean voice, an inner city Black man from the South

  THE 2026-08-26 RULING FILLED THE EMPTY SLOT: the old lock was only "clean",
  which the block below records as an AUDIO-QUALITY note -- the character/
  accent/origin slot of the five was never written, so Higgsfield defaulted to
  a generic movie tough-guy read. It now carries the man.
  ⚠️ THE NEGATIVE HALF OF HIS RULING ("not some white tough guy from the
  movies") IS THE RULING, NOT THE LOCK -- per the words-you-summon rule it
  never goes into a prompt, because writing it summons it. Steer positive.
'''

if not DISK.exists():
    sys.exit("canon file missing")
text = DISK.read_text(encoding="utf-8")

if NEW_BLOCK in text:
    print("already applied -- nothing to do")
else:
    if OLD_BLOCK not in text:
        sys.exit("REFUSING: the 2026-08-20 B Dubb voice block is not "
                 "byte-identical to what this script expects. Check by hand.")
    backup = ROOT / "data" / "backup_disk_canon_before_bdubb_voice_direction_2026-08-26.md"
    shutil.copy2(DISK, backup)
    print(f"backed up disk canon -> {backup.name}")
    text = text.replace(OLD_BLOCK, NEW_BLOCK, 1)
    assert text.count(NEW_BLOCK) == 1, "splice did not land exactly once"
    DISK.write_text(text, encoding="utf-8")
    print(f"disk canon updated ({len(text):,} chars)")

con = sqlite3.connect(DB)
before = con.execute("SELECT content FROM facts WHERE id=?", (FACT_ID,)).fetchone()[0]
bfile = ROOT / "data" / "backup_fact592_before_bdubb_voice_direction_2026-08-26.md"
if not bfile.exists():
    bfile.write_text(before, encoding="utf-8")
    print(f"backed up fact {FACT_ID} -> {bfile.name}")
disk_now = DISK.read_text(encoding="utf-8")
con.execute("UPDATE facts SET content=? WHERE id=?", (disk_now, FACT_ID))
con.commit()
after = con.execute("SELECT content FROM facts WHERE id=?", (FACT_ID,)).fetchone()[0]
assert after == disk_now, "fact 592 and disk canon differ after sync"
print(f"fact {FACT_ID} synced -- byte-identical at {len(after):,} chars")
assert "inner city black man from the south" in after
assert "clean voice, an inner city Black man from the South" in after
print("VERIFIED: ruling recorded verbatim + paste lock present in both copies")
