"""Merge the global instructions, the project instructions and every memory
note into ONE file that belongs to the build: BARRYS-AGENTS.md (Barry,
2026-09-06: "it stays with my agents build... labeled Barry's agents.md").
Re-runnable; also copies the memory notes to docs/agents-memory/."""
import glob
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.expanduser("~")
GLOBAL = os.path.join(HOME, ".claude", "CLAUDE.md")
PROJECT = os.path.join(ROOT, "CLAUDE.md")
MEMDIR = os.path.join(HOME, ".claude", "projects", "C--Users-Owner-Desktop-AgentCompanyBackend", "memory")
DST = os.path.join(ROOT, "docs", "agents-memory")
BAR = "=" * 78


def read(p):
    return open(p, encoding="utf-8").read() if os.path.isfile(p) else ""


os.makedirs(DST, exist_ok=True)
n = 0
for f in glob.glob(os.path.join(MEMDIR, "*.md")):
    shutil.copy2(f, DST)
    n += 1
notes = [f for f in sorted(glob.glob(os.path.join(DST, "*.md"))) if not f.endswith("MEMORY.md")]
mem = "\n\n".join(read(f) for f in notes)

out = "\n".join([
    "# BARRY'S AGENTS -- the complete build record",
    "",
    "This file belongs to the build, not to any AI vendor. It is the merged copy of the two",
    "instruction files and every memory note that used to live under the user's .claude folder.",
    "Assembled 2026-09-06 on Barry's instruction: \"it stays with my agents build\".",
    "Any assistant, person, or future tool working on this office reads THIS file first.",
    "The individual memory notes are in docs/agents-memory/.",
    "",
    BAR, "# PART 1 -- THE BUILD (was the global instructions file)", BAR, "",
    read(GLOBAL),
    "", BAR, "# PART 2 -- SESSION RECORD (was the project instructions file)", BAR, "",
    read(PROJECT),
    "", BAR, "# PART 3 -- STANDING LESSONS (the memory notes)", BAR, "",
    mem,
])
open(os.path.join(ROOT, "BARRYS-AGENTS.md"), "w", encoding="utf-8").write(out)
print(f"BARRYS-AGENTS.md {len(out):,} chars; {n} memory notes copied to docs/agents-memory/")
