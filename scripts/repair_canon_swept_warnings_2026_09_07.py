"""Repair the canon sentences that an earlier handle sweep inverted.

FOUND 2026-09-07 while doing Barry's @b-dubb fix. A previous find-and-replace
swept handles to their real Higgsfield element names (@Keth -> @keth, @Vorshara
-> @lady-vor-shara-vel, @B-DUBB-new -> @b-dubb). The renames themselves are
CORRECT and verified against comfy_image: every one still resolves to the right
local LoRA. But the sweep also rewrote the handle INSIDE warnings whose whole
job is to name the handle that does NOT work -- so the canon now tells the
reader that the CORRECT handle "resolves to NOTHING", and that the correct
handle "IS WRONG AND HAS ALWAYS BEEN WRONG".

This is the 2026-08-20 'stocky' lesson repeating exactly: a document whose job
includes recording superseded/wrong wording must never be blind-swept for that
wording.

Restores the wrong-handle names inside those warnings ONLY (verbatim from the
pre-sweep disk copy). Touches no spec, no description, no ruling.

Applies to BOTH canon copies and asserts they stay byte-identical.
Re-runnable: every replace is checked for its expected count first.
"""
import sys
import os
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import memory  # noqa: E402

REPO = os.path.join(os.path.dirname(__file__), "..")
CANON = os.path.join(REPO, "data", "barry-character-canon.md")
BACKUP_DIR = os.path.join(REPO, "data", "backup_bdubb_handle_2026-09-07")

REPAIRS = [
    # the substitution rule told you to swap a handle for itself
    ('  @b-dubb, you type @b-dubb. Where it says "alien pistol", name the weapon',
     '  @BDUBB or @B-DUBB-new, you type @b-dubb. Where it says "alien pistol", name the weapon'),
    # the warning declared the CORRECT handle wrong
    ("**@lady-vor-shara-vel IS WRONG AND HAS ALWAYS BEEN WRONG.**",
     "**@Vorshara IS WRONG AND HAS ALWAYS BEEN WRONG.**"),
    # ...and said the correct handle resolves to nothing
    ('"@lady-vor-shara-vel" resolves to NOTHING and the reference is silently lost',
     '"@Vorshara" resolves to NOTHING and the reference is silently lost'),
    # use-this/not-that table said use X instead of X
    ("| `@lady-vor-shara-vel` | ~~@lady-vor-shara-vel~~ |",
     "| `@lady-vor-shara-vel` | ~~@Vorshara~~ |"),
    # the Yannah warning pointed at the wrong precedent
    ("way `@lady-vor-shara-vel` did. Barry has not confirmed this one",
     "way `@Vorshara` did. Barry has not confirmed this one"),
    # alias list listed the primary handle as its own alias
    ("(also accepted: @Barry, @Vor, @Shara, @lady-vor-shara-vel",
     "(also accepted: @Barry, @Vor, @Shara, @LadyVorshara"),
]

RETIREMENT = """
--- B DUBB HANDLE, RETIREMENT ON RECORD (Barry 2026-08-29, restated 2026-09-07) ---
THE ONLY B DUBB HANDLE IS @b-dubb. He deleted the B-DUBB-new Higgsfield element
outright ("b-dubb new is a wash. im deleting it") and restated it 2026-09-07:
"no b dub new was messing up so we are going with the original @b-dubb."
@BDUBB and @B-DUBB-new are both RETIRED. Kept on record here so no older file
re-promotes them; never type either one. Verified 2026-09-07: @b-dubb resolves
to bdubb_character.safetensors locally, so it works in both destinations.
"""

with memory.get_db() as conn:
    text = conn.execute("SELECT content FROM facts WHERE id = 592").fetchone()["content"]

before = text
applied, skipped = [], []
for old, new in REPAIRS:
    n = text.count(old)
    if n == 0:
        skipped.append(f"already repaired: {old[:60]}...")
        continue
    assert n == 1, f"expected 1 of {old[:60]!r}, found {n}"
    text = text.replace(old, new)
    applied.append(old[:70])

anchor = "NOT RENAMED, so do not change them: @keth and @lady-vor-shara-vel."
if "B DUBB HANDLE, RETIREMENT ON RECORD" not in text:
    assert anchor in text, "retirement anchor not found"
    text = text.replace(anchor, anchor + "\n" + RETIREMENT, 1)
    applied.append("retirement record added")

if text == before:
    print("nothing to change -- already repaired")
else:
    shutil.copy2(CANON, os.path.join(BACKUP_DIR, "barry-character-canon.BEFORE_REPAIR.md"))
    with memory.get_db() as conn:
        conn.execute("UPDATE facts SET content = ? WHERE id = 592", (text,))
    tmp = CANON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, CANON)

print("APPLIED:")
for a in applied:
    print("  -", a)
for s in skipped:
    print("  (skip)", s)

# verify
with memory.get_db() as conn:
    f592 = conn.execute("SELECT content FROM facts WHERE id = 592").fetchone()["content"]
disk = open(CANON, "r", encoding="utf-8").read()
print()
print("VERIFY")
print("  disk == fact 592                :", disk == f592)
print("  'correct handle resolves to nothing' gone:",
      '"@lady-vor-shara-vel" resolves to NOTHING' not in f592)
print("  'correct handle IS WRONG' gone  :",
      "**@lady-vor-shara-vel IS WRONG" not in f592)
print("  swap-rule self-reference gone   :",
      "@b-dubb, you type @b-dubb" not in f592)
print("  retirement recorded             :", "RETIREMENT ON RECORD" in f592)
print("  chars                           :", len(f592))
