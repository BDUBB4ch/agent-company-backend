"""Sync Elliot's Seedance / directing skills from disk into his brain.

Three skills, deliberately split one-concern-each (Barry 2026-08-13:
"just the stuff we need, but know it all"):

  seedance-prompting.md            PINNED   the machine grammar (per-shot)
  scifi-action-drama-directing.md  PINNED   the craft (what the tools serve)
  oneiric-production-method.md     ON-DEMAND planning depth, routed by USE WHEN

Edit the files in knowledge/, re-run this, all stay in sync. Re-runnable.
Pre-2.5 backup: data/backup_seedance_prompting_before_25_2026-08-13.md
"""
import sys, os, sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import memory  # noqa: E402
import agents  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
KNOW = os.path.join(ROOT, "knowledge")
OFFICE = "MovieDirector"
CATEGORY = f"private:{OFFICE}"

SKILLS = [
    ("seedance-prompting.md", "Seedance 2.5 prompting -- per-shot grammar for Higgsfield"),
    ("scifi-action-drama-directing.md", "Directing sci-fi action and drama -- craft, then how it becomes a prompt"),
    ("oneiric-production-method.md", "ONEIRIC production method -- assets, character sheets, diagram staging, scale numbers"),
]

db_path = memory.DB_PATH if hasattr(memory, "DB_PATH") else os.path.join(ROOT, "data", "memory.db")
db = sqlite3.connect(db_path)

for source_name, title in SKILLS:
    content = open(os.path.join(KNOW, source_name), encoding="utf-8").read()
    row = db.execute(
        "SELECT id, length(content) FROM facts WHERE source_name=? AND category=? AND status='active'",
        (source_name, CATEGORY),
    ).fetchone()
    if row:
        db.execute("UPDATE facts SET content=? WHERE id=?", (content, row[0]))
        db.commit()
        print(f"  updated  id={row[0]:<4} {source_name:<34} {row[1]:>6} -> {len(content)} chars")
    else:
        memory.add_fact(category=CATEGORY, content=content, source_name=source_name, title=title)
        nid = db.execute(
            "SELECT id FROM facts WHERE source_name=? AND category=? AND status='active'",
            (source_name, CATEGORY),
        ).fetchone()
        print(f"  CREATED  id={nid[0] if nid else '?':<4} {source_name:<34} {len(content)} chars")

# --- verify -------------------------------------------------------------
pins = agents.PINNED_SKILLS.get(agents.MOVIE_ID, [])
block = memory.pinned_skills_block(OFFICE, pins)
print(f"\nElliot pinned block: {len(block)} chars "
      f"(~{round(len(block)/4/65536*100,1)}% of his 65,536-token window)")
for name in pins:
    print("   ", name, "->", "LOADED" if f"# {name}" in block or name in block else "MISSING")

brain = memory.brain_context_block(OFFICE, pinned_titles=pins)
print(f"\nalways-on brain block: {len(brain)} chars")
print("index routing lines now visible to Elliot:")
for line in brain.splitlines():
    if line.startswith("- ") and " -- " in line and "PINNED" not in line:
        print("   ", line[:150])

# The on-demand one must NOT be pinned, but MUST be routable.
print("\noneiric pinned?", any("oneiric" in p for p in pins), "(expected False)")
print("oneiric has USE WHEN in index?",
      any("oneiric-production-method -- " in l for l in brain.splitlines()))
