"""Push the disk canon into fact 592 and assert the two are byte-identical.

Canon lives in TWO places (data/barry-character-canon.md and facts.id=592) and
they have drifted before. This is the sync half of the 2026-08-25 Glock ->
@B-Dubb's-Banger rename: the disk file was edited by hand, this pushes it.

Re-runnable. Asserts before and after; refuses to write if the disk file has
lost the new handle or still carries the trademark on B Dubb's gun.
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DISK = ROOT / "data" / "barry-character-canon.md"
DB = ROOT / "data" / "brain.db"
FACT_ID = 592

disk = DISK.read_text(encoding="utf-8")

# Guard: the rename must actually be in the file we are about to push.
if "@B-Dubb's-Banger" not in disk:
    sys.exit("REFUSING: disk canon has no @B-Dubb's-Banger -- wrong file?")

# The only Glock references left should be the readability-anchor lines inside
# Barry's own verbatim prop prompts for the ALIEN weapons. Three, no more.
glock = disk.count("Glock")
if glock != 3:
    sys.exit(f"REFUSING: expected 3 remaining Glock hits (alien silhouette "
             f"anchors), found {glock}. Check by hand before syncing.")

con = sqlite3.connect(DB)
before = con.execute("select content from facts where id=?", (FACT_ID,)).fetchone()[0]
print(f"fact {FACT_ID} before: {len(before)} chars, {before.count('Glock')} Glock")
print(f"disk          now:    {len(disk)} chars, {disk.count('Glock')} Glock")

con.execute("update facts set content=? where id=?", (disk, FACT_ID))
con.commit()

after = con.execute("select content from facts where id=?", (FACT_ID,)).fetchone()[0]
assert after == disk, "sync failed -- fact and disk still differ"
print(f"fact {FACT_ID} after:  {len(after)} chars -- BYTE-IDENTICAL to disk")
print(f"Banger handle occurrences: {after.count(chr(64) + chr(66) + '-Dubb')}")
