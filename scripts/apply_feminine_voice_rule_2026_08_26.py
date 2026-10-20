"""Barry, 2026-08-26, minutes after directing the five: "all the women should
still sound femanine, not masculine"

Blanket rule over the four women (@Bia-2, @Yannah, @Tazz, @Vorshara).
"feminine" leads each of their paste locks; "not masculine" is the ruling and
never prompt text (words-you-summon). This matters most for Tazz (mid-range +
husky) and Vor'Shara (gritty + deeper) -- the two directions a generator
could otherwise read as license to go masculine.

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

LOCK_EDITS = [
    ("    gritty, vengeful, a little deeper; deliberate, never slow, quickening slightly when angered; careful delivery, open hatred when speaking to B Dubb",
     "    feminine; gritty, vengeful, a little deeper; deliberate, never slow, quickening slightly when angered; careful delivery, open hatred when speaking to B Dubb"),
    ("    calm, mid-range, the faintest husky edge",
     "    feminine; calm, mid-range, the faintest husky edge"),
    ("    smart but sexy; normal speaking pace, witty, sometimes snarky",
     "    feminine; smart but sexy; normal speaking pace, witty, sometimes snarky"),
    ("    direct, the leader; measured, with authority -- when she gives an order it lands, no questions",
     "    feminine; direct, the leader; measured, with authority -- when she gives an order it lands, no questions"),
]

RULE_MARK = 'THE WOMEN SOUND FEMININE -- BARRY, 2026-08-26'
RULE = f'''
---------------------------------------------------------------
*** {RULE_MARK}, verbatim: "all the women should
still sound femanine, not masculine" ***
Blanket rule over @Bia-2, @Yannah, @Tazz and @Vorshara -- "feminine" now leads
each of their locks. It exists because two of the same day's directions could
otherwise drift: Tazz's mid-range + husky and Vor'Shara's gritty + deeper are
NOT license for a masculine read. Per words-you-summon, "not masculine" never
goes into a prompt -- steer with the positive word only.
---------------------------------------------------------------
'''

text = DISK.read_text(encoding="utf-8")
if RULE_MARK in text:
    print("already applied -- verifying sync only")
else:
    for old, _ in LOCK_EDITS:
        if old not in text:
            sys.exit(f"REFUSING: lock line not found byte-identical: {old[:60]}...")
    shutil.copy2(DISK, ROOT / "data" / "backup_disk_canon_before_feminine_rule_2026-08-26.md")
    for old, new in LOCK_EDITS:
        text = text.replace(old, new, 1)
    anchor = "  *** B DUBB'S VOICE IS A CREATED VOICE, MADE FROM BARRY'S -- RULED 2026-08-20. ***"
    assert anchor in text
    text = text.replace(anchor, RULE + "\n" + anchor, 1)
    DISK.write_text(text, encoding="utf-8")
    print(f"disk canon updated ({len(text):,} chars)")

con = sqlite3.connect(DB)
disk_now = DISK.read_text(encoding="utf-8")
con.execute("UPDATE facts SET content=? WHERE id=?", (disk_now, FACT_ID))
con.commit()
after = con.execute("SELECT content FROM facts WHERE id=?", (FACT_ID,)).fetchone()[0]
assert after == disk_now
assert after.count("feminine;") == 4, f"expected 4 feminine locks, got {after.count('feminine;')}"
print(f"fact {FACT_ID} synced byte-identical at {len(after):,} chars -- 4 feminine locks verified")
