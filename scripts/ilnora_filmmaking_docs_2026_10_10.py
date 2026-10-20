"""2026-10-10 (Barry: "she is a film maker too" / "production quality"): sync Ilnora's three corrected video docs to
their brain facts and add her new my-filmmaking skill. Diff first; --apply writes (brain backed up first)."""
import difflib
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import config  # noqa: E402
import memory  # noqa: E402

K = os.path.join(ROOT, "knowledge", "creative")
DOCS = {4904: ("make-epic-videos.md", "MAKING YOUR VIDEOS EPIC"),
        4702: ("make-video-masterfully.md", "MAKING YOUR VIDEOS MASTERFULLY"),
        4919: ("my-toolkit.md", "MY TOOLKIT")}
NEW = ("my-filmmaking.md", "MY FILMMAKING")
apply = "--apply" in sys.argv

with memory.get_db() as c:
    rows = {i: c.execute("SELECT content, source_name, category, status FROM facts WHERE id = ?", (i,)).fetchone()
            for i in DOCS}
    have_new = c.execute("SELECT id FROM facts WHERE category = 'private:ilnora' AND source_name = ? "
                         "AND status = 'active'", (NEW[0],)).fetchall()
for i, (fn, title) in DOCS.items():
    content, src, cat, status = rows[i]
    assert src == fn and cat == "private:ilnora" and status == "active", (i, src, cat, status)
    new = memory._ensure_titled(open(os.path.join(K, fn), encoding="utf-8").read(), title, fn, cat)
    diff = list(difflib.unified_diff(content.splitlines(), new.splitlines(), lineterm="", n=0))
    print(f"=== fact {i} {fn}: {len(diff)} diff lines")
    for line in diff:
        print("   ", line[:400])
print("new skill already in brain:", [r[0] for r in have_new])
if apply:
    bak = os.path.join(config.DATA_DIR, "brain_backup_before_filmmaking_2026-10-10.db")
    shutil.copy2(config.DB_PATH, bak)
    print("backup:", bak)
    with memory.get_db() as c:
        for i, (fn, title) in DOCS.items():
            new = memory._ensure_titled(open(os.path.join(K, fn), encoding="utf-8").read(), title, fn, "private:ilnora")
            c.execute("UPDATE facts SET content = ? WHERE id = ?", (new, i))
    if not have_new:
        memory.add_fact("private:ilnora", open(os.path.join(K, NEW[0]), encoding="utf-8").read(),
                        source_name=NEW[0], title=NEW[1])
    print("applied")
