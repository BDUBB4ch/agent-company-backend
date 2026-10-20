"""ALL FIVE REMAINING VOICES DIRECTED -- Barry, 2026-08-26, verbatim:

"not slow but deliberate, slightly fast when angered or annoyed. for Vor and
keth carful and but hateful, towards b dubb for now. Tazz is calm, not a deep
voice , but not light. slightly husky, but not really. Yannah is she has a
normal speed of her speech ,but shes witty and sometimes snarky. Bia is
measured, but with authority, when she gives orders, its like oh shit Bia
gave an order type feel. Its direct and no questions, Keths pitch should be
nasally and not robotic or mechanical, not synthed anymore, raspy too"

PARSE (Claude's reading, recorded so nothing is silently interpreted):
- Vor'Shara: not slow but deliberate; slightly fast when angered/annoyed;
  careful but hateful toward B Dubb, for now (shared with Keth).
- Keth: careful but hateful toward B Dubb for now; pitch NASALLY and RASPY;
  explicitly NOT robotic/mechanical/synthesized anymore.
- Tazz: calm; not deep, not light; slightly husky "but not really" (barely).
- Yannah: normal speaking speed; witty, sometimes snarky.
- Bia: measured, with authority; an order lands "oh shit Bia gave an order";
  direct, no questions.

TWO SUPERSESSIONS, his newest word wins, old words kept on record:
- Tazz "deeper" (2026-08-20) -> "not a deep voice, but not light". The pitch
  ladder's 135 Hz target for her is DEAD -- re-derive when she regenerates.
- Keth "slightly synthesized" (2026-08-20) -> "not synthed anymore". The
  execution note "let the artifacts show" no longer applies to him -- his
  regeneration wants a genuinely nasally/raspy voice, not a processed shift.

Paste locks are POSITIVE-ONLY (words-you-summon): "not robotic / not synthed"
is the ruling, never the prompt. Where his direction was stated as a negative
("not deep, not light") the lock renders the positive middle ("mid-range")
with the verbatim words recorded directly above it.

House pattern: assert anchors, backup both copies, splice, sync fact 592,
verify byte-identical. Re-runnable.
"""
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DISK = ROOT / "data" / "barry-character-canon.md"
DB = ROOT / "data" / "brain.db"
FACT_ID = 592

VERBATIM = '''"not slow but deliberate, slightly fast when angered or annoyed. for Vor and
keth carful and but hateful, towards b dubb for now. Tazz is calm, not a deep
voice , but not light. slightly husky, but not really. Yannah is she has a
normal speed of her speech ,but shes witty and sometimes snarky. Bia is
measured, but with authority, when she gives orders, its like oh shit Bia
gave an order type feel. Its direct and no questions, Keths pitch should be
nasally and not robotic or mechanical, not synthed anymore, raspy too"'''

# (old exact block, new block) -- each asserted before writing
EDITS = [
    (
        '''@KETH -- DIRECTED 2026-08-20. HIS WORDS, both passes the same day:
  "higher pitched and slightly doubled" + "well make it sound synthesized slightly."
---------------------------------------------------------------
  LOCK TEXT (paste verbatim into the prompt):
    higher-pitched voice, slightly synthesized
''',
        '''@KETH -- DIRECTED 2026-08-20, RE-DIRECTED 2026-08-26.
  2026-08-20: "higher pitched and slightly doubled" + "well make it sound synthesized slightly."
  2026-08-26: "Keths pitch should be nasally and not robotic or mechanical, not
  synthed anymore, raspy too" + (shared with Vor'Shara) "carful and but hateful,
  towards b dubb for now"
  *** "SYNTHESIZED" IS SUPERSEDED -- his 2026-08-26 words explicitly remove it.
  The old execution plan ("shift and let the artifacts show") no longer applies:
  Keth's voice wants to be GENUINELY nasally and raspy, not processed. The
  hatred toward @B-DUBB-new is story-current ("for now") -- expect it to change
  when the story does. ***
---------------------------------------------------------------
  LOCK TEXT (paste verbatim into the prompt):
    higher-pitched, nasally, raspy; careful delivery, open hatred when speaking to B Dubb
''',
    ),
    (
        '''@VORSHARA -- DIRECTED 2026-08-20. HIS WORDS: "i want this voice to sound more
gritty and vengefull, for lady vor and a lil deeper."
---------------------------------------------------------------
  LOCK TEXT (paste verbatim into the prompt):
    gritty, vengeful, a little deeper
''',
        '''@VORSHARA -- DIRECTED 2026-08-20, EXPANDED 2026-08-26.
  2026-08-20: "i want this voice to sound more gritty and vengefull, for lady
  vor and a lil deeper."
  2026-08-26: "not slow but deliberate, slightly fast when angered or annoyed"
  + (shared with Keth) "carful and but hateful, towards b dubb for now"
  The hatred toward @B-DUBB-new is story-current ("for now").
---------------------------------------------------------------
  LOCK TEXT (paste verbatim into the prompt):
    gritty, vengeful, a little deeper; deliberate, never slow, quickening slightly when angered; careful delivery, open hatred when speaking to B Dubb
''',
    ),
    (
        '''@TAZZ -- DIRECTED 2026-08-20. HIS WORDS: "Tazz can go deeper too."
---------------------------------------------------------------
  LOCK TEXT (paste verbatim into the prompt):
    deeper
''',
        '''@TAZZ -- DIRECTED 2026-08-20, RE-DIRECTED 2026-08-26.
  2026-08-20: "Tazz can go deeper too."
  2026-08-26: "Tazz is calm, not a deep voice , but not light. slightly husky,
  but not really."
  *** "DEEPER" IS SUPERSEDED -- she is mid-range now, and the pitch ladder's
  135 Hz target for her is DEAD. Re-derive her target from the new direction
  when she is regenerated; do not pitch-shift toward 135. "Slightly husky, but
  not really" means the huskiness is a trace, not a texture -- if a render
  sounds smoky, it overshot. ***
---------------------------------------------------------------
  LOCK TEXT (paste verbatim into the prompt):
    calm, mid-range, the faintest husky edge
''',
    ),
    (
        '''@YANNAH -- DIRECTED 2026-08-20. HIS WORDS: "Yannah should sound smart but sexy."
---------------------------------------------------------------
  LOCK TEXT (paste verbatim into the prompt):
    smart but sexy
''',
        '''@YANNAH -- DIRECTED 2026-08-20, EXPANDED 2026-08-26.
  2026-08-20: "Yannah should sound smart but sexy."
  2026-08-26: "Yannah is she has a normal speed of her speech ,but shes witty
  and sometimes snarky."
---------------------------------------------------------------
  LOCK TEXT (paste verbatim into the prompt):
    smart but sexy; normal speaking pace, witty, sometimes snarky
''',
    ),
    (
        '''@BIA-2 -- DIRECTED 2026-08-20. HIS WORDS: "Bia is the leader. she more direct."
---------------------------------------------------------------
  LOCK TEXT (paste verbatim into the prompt):
    direct, the leader
''',
        '''@BIA-2 -- DIRECTED 2026-08-20, EXPANDED 2026-08-26.
  2026-08-20: "Bia is the leader. she more direct."
  2026-08-26: "Bia is measured, but with authority, when she gives orders, its
  like oh shit Bia gave an order type feel. Its direct and no questions"
---------------------------------------------------------------
  LOCK TEXT (paste verbatim into the prompt):
    direct, the leader; measured, with authority -- when she gives an order it lands, no questions
''',
    ),
]

NEW_SECTION_MARK = "ALL FIVE RE-DIRECTED IN ONE PASS -- BARRY, 2026-08-26"
SECTION = f'''
---------------------------------------------------------------
*** {NEW_SECTION_MARK}. HIS FULL MESSAGE, VERBATIM: ***
{VERBATIM}
The per-character blocks above each carry their slice of this ruling plus the
parse notes. Two supersessions came out of it: Tazz is no longer "deeper"
(135 Hz ladder target dead) and Keth is no longer "synthesized" (the
let-the-artifacts-show execution note no longer applies to him). Locks are
positive-only per the words-you-summon rule -- "not robotic / not synthed /
not deep" are rulings, never prompt text.
---------------------------------------------------------------
'''

text = DISK.read_text(encoding="utf-8")
if NEW_SECTION_MARK in text:
    print("already applied -- verifying sync only")
else:
    for old, _ in EDITS:
        if old not in text:
            sys.exit(f"REFUSING: expected block not found byte-identical:\n{old[:90]}...")
    backup = ROOT / "data" / "backup_disk_canon_before_five_voices_2026-08-26.md"
    shutil.copy2(DISK, backup)
    print(f"backed up -> {backup.name}")
    for old, new in EDITS:
        text = text.replace(old, new, 1)
    # the combined verbatim message rides at the end of the Voice Bible's
    # per-character blocks -- right after the B Dubb block, before the
    # created-voice ruling
    anchor = "  *** B DUBB'S VOICE IS A CREATED VOICE, MADE FROM BARRY'S -- RULED 2026-08-20. ***"
    assert anchor in text, "B Dubb created-voice anchor missing"
    text = text.replace(anchor, SECTION + "\n" + anchor, 1)
    DISK.write_text(text, encoding="utf-8")
    print(f"disk canon updated ({len(text):,} chars)")

con = sqlite3.connect(DB)
before = con.execute("SELECT content FROM facts WHERE id=?", (FACT_ID,)).fetchone()[0]
bfile = ROOT / "data" / "backup_fact592_before_five_voices_2026-08-26.md"
if not bfile.exists():
    bfile.write_text(before, encoding="utf-8")
disk_now = DISK.read_text(encoding="utf-8")
con.execute("UPDATE facts SET content=? WHERE id=?", (disk_now, FACT_ID))
con.commit()
after = con.execute("SELECT content FROM facts WHERE id=?", (FACT_ID,)).fetchone()[0]
assert after == disk_now, "fact 592 drifted from disk"
for probe in ("nasally, raspy", "calm, mid-range", "oh shit Bia gave an order",
              "witty, sometimes snarky", "quickening slightly when angered"):
    assert probe in after, f"missing: {probe}"
print(f"fact {FACT_ID} synced, byte-identical at {len(after):,} chars")
print("VERIFIED: all five rulings + locks present in both copies")
