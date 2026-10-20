"""Seed Sophie's upgrade: coding-craft + defensive-security into
domain:engineering (Barry, 2026-08-29: "I want sophie to have as much of your
coding knowledge and skills as possible without breaking my build... i need
her to truly know how to code, and know cyber security").

Both on-demand with USE WHEN routing. coding-craft additionally gets PINNED
for Sophie (agents.py edit, same session) -- method she carries every message.
Re-runnable: upserts by (source_name, category).
"""
import sys, os, sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import memory  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
CATEGORY = "domain:engineering"
FILES = [
    ("coding-craft.md", "Coding craft -- read first, smallest change, one variable per experiment, verify behavior, this build's physics"),
    ("defensive-security.md", "Defensive security -- credentials, least privilege, the store's real attack surface, offline mode as a boundary"),
]

db = sqlite3.connect(memory.DB_PATH)
for fname, title in FILES:
    content = open(os.path.join(ROOT, "knowledge", "engineering", fname),
                   encoding="utf-8").read()
    row = db.execute(
        "SELECT id, length(content) FROM facts WHERE source_name=? AND category=? AND status='active'",
        (fname, CATEGORY)).fetchone()
    if row:
        db.execute("UPDATE facts SET content=? WHERE id=?", (content, row[0]))
        db.commit()
        print(f"updated id={row[0]} {fname}: {row[1]} -> {len(content)} chars")
    else:
        memory.add_fact(category=CATEGORY, content=content,
                        source_name=fname, title=title)
        nid = db.execute(
            "SELECT id FROM facts WHERE source_name=? AND category=? AND status='active'",
            (fname, CATEGORY)).fetchone()
        print(f"CREATED id={nid[0] if nid else '?'} {fname}: {len(content)} chars")

brain = memory.brain_context_block("Engineer")
for fname, _ in FILES:
    print(fname[:-3], "routed for Sophie:", fname[:-3] in brain)
