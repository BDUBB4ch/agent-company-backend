"""Barry, 2026-09-07: "no b dub new was messing up so we are going with the
original @b-dubb" -> "fix it".

MEASURED FIRST: fact 592 (the canon Elliot actually reads) was ALREADY correct --
zero @B-DUBB-new. The DISK copy had drifted 10 mentions behind, which is the
documented two-copies drift trap. So this syncs disk to the fact, fixes one line
the earlier sweep broke, and corrects the three ACTIVE tables in the build docs.

Historical session records that mention @B-DUBB-new are LEFT ALONE -- a document
whose job includes recording superseded wording must never be blind-swept (the
2026-08-20 'stocky' lesson).

Re-runnable. Backs up every file before writing. Asserts each replace landed.
"""
import sys
import os
import shutil
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import memory  # noqa: E402

REPO = os.path.join(os.path.dirname(__file__), "..")
STAMP = "2026-09-07"
BACKUP_DIR = os.path.join(REPO, "data", f"backup_bdubb_handle_{STAMP}")
os.makedirs(BACKUP_DIR, exist_ok=True)

# The line the earlier sweep broke: it replaced the handle AND the thing the
# handle replaces, leaving "use instead of @b-dubb" pointing at itself.
BROKEN = "@b-dubb               B Dubb       (use instead of @b-dubb)"
FIXED = "@b-dubb               B Dubb       (use instead of @BDUBB and @B-DUBB-new, both retired)"

RETIREMENT_NOTE = """
--- HANDLE RETIREMENT, Barry 2026-08-29, restated 2026-09-07 ---
@B-DUBB-new is DEAD. He deleted that Higgsfield element outright ("b-dubb new
is a wash. im deleting it"), and restated it 2026-09-07: "no b dub new was
messing up so we are going with the original @b-dubb." @BDUBB is retired too.
THE ONLY B DUBB HANDLE IS @b-dubb. Both old spellings are kept on record here
so nothing re-promotes them from an older file; never type either one.
"""

changed = []


def backup(path):
    if os.path.exists(path):
        shutil.copy2(path, os.path.join(BACKUP_DIR, os.path.basename(path)))


def patch_file(path, pairs, label):
    """pairs = [(old, new, expected_count)]"""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    backup(path)
    for old, new, expected in pairs:
        found = text.count(old)
        assert found == expected, f"{label}: expected {expected} of {old!r}, found {found}"
        text = text.replace(old, new)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    changed.append(f"{label} ({path})")


# ---------------------------------------------------------------- 1. the canon
# fact 592 is the SURVIVOR (correct + newer). Disk gets synced to it, then the
# one broken line is fixed in both so they stay byte-identical.
with memory.get_db() as conn:
    fact = conn.execute("SELECT content FROM facts WHERE id = 592").fetchone()["content"]

assert fact.count("B-DUBB-new") == 0, "fact 592 unexpectedly still has the dead handle"

canon_path = os.path.join(REPO, "data", "barry-character-canon.md")
backup(canon_path)

if BROKEN in fact:
    fact = fact.replace(BROKEN, FIXED)
if "HANDLE RETIREMENT, Barry 2026-08-29" not in fact:
    fact = fact.replace(
        "NOT RENAMED, so do not change them: @Keth and @Vorshara.",
        "NOT RENAMED, so do not change them: @Keth and @Vorshara.\n" + RETIREMENT_NOTE,
        1,
    )

with memory.get_db() as conn:
    conn.execute(
        "UPDATE facts SET content = ? WHERE id = 592", (fact,)
    )
tmp = canon_path + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    f.write(fact)
os.replace(tmp, canon_path)
changed.append("canon: fact 592 + disk copy synced, broken line fixed, retirement recorded")

# --------------------------------------------------- 2. build docs, ACTIVE only
patch_file(
    "C:/Users/Owner/.claude/CLAUDE.md",
    [
        ("| B Dubb | `@B-DUBB-new` (was `@BDUBB`) |",
         "| B Dubb | `@b-dubb` (`@BDUBB` and `@B-DUBB-new` both RETIRED -- he deleted that element 2026-08-29) |", 1),
        ("| `@B-DUBB-new` | **B-Dubb-Voice** (his own) |",
         "| `@b-dubb` | **B-Dubb-Voice** (his own) |", 1),
        ("| @B-DUBB-new | `clean` |", "| @b-dubb | `clean` |", 1),
    ],
    "global CLAUDE.md active tables",
)

# ------------------------------------------------------ 3. knowledge disk files
patch_file(
    os.path.join(REPO, "knowledge", "seedance-prompting.md"),
    [
        ("| @B-DUBB-new | clean voice, an inner city Black man from the South |",
         "| @b-dubb | clean voice, an inner city Black man from the South |", 1),
        ("VO (@B-DUBB-new, clean voice, an inner city Black man from the South)",
         "VO (@b-dubb, clean voice, an inner city Black man from the South)", 1),
    ],
    "knowledge/seedance-prompting.md",
)

# ------------------------------------------------- 4. the one live fact with it
with memory.get_db() as conn:
    row = conn.execute(
        "SELECT id, content FROM facts WHERE source_name = 'using-character-voices.md' "
        "AND status = 'active'"
    ).fetchone()
    if row and "B-DUBB-new / B-Dubb-new / BDUBB / B DUBB | **@b-dubb**" in row["content"]:
        # that row is the dead-handle ALIAS table -- correct as written, leave it.
        changed.append("fact 1585 using-character-voices: alias table correct, left as-is")

print("CHANGED:")
for c in changed:
    print(" -", c)

# ----------------------------------------------------------------- 5. verify
with memory.get_db() as conn:
    f = conn.execute("SELECT content FROM facts WHERE id = 592").fetchone()["content"]
disk = open(canon_path, "r", encoding="utf-8").read()
print()
print("VERIFY")
print("  fact 592 dead-handle hits :", f.count("B-DUBB-new"))
print("  disk canon dead-handle hits:", disk.count("B-DUBB-new"))
print("  disk == fact 592           :", disk == f)
print("  broken self-referential line gone:", BROKEN not in f and BROKEN not in disk)
print("  retirement recorded        :", "HANDLE RETIREMENT" in f)
print("  backups in                 :", BACKUP_DIR)
