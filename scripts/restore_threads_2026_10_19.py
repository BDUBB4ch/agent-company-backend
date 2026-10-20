"""Put every seat's conversation thread back (Barry 2026-10-19: "her home thread, put it back" / "did you delete all
their home threads?"). The 10-17 'clean threads' measurement rerun wiped all ten seats' threads (home + work) and no
per-thread JSON backup was made. Source: the newest full brain backup, 2026-10-17 02:47 local
(data/backup_brain_before_sophie_mp_skills_2026-10-17.db, 123 rows). Rows written between that backup and the wipe
(~15:00 on 10-17) are gone. Per agent: backup rows + live rows not already in the backup, sorted by time, re-inserted
so id order = time order (the thread reader orders by id). Live brain backed up first via the SQLite backup API."""
import os, sqlite3, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
import config, memory  # noqa: E402

SRC = os.path.join(config.DATA_DIR, "backup_brain_before_sophie_mp_skills_2026-10-17.db")
SAFE = os.path.join(config.DATA_DIR, "brain_backup_before_thread_restore_2026-10-19.db")
apply = "--apply" in sys.argv

src = sqlite3.connect(SRC); src.row_factory = sqlite3.Row
old = [dict(r) for r in src.execute("SELECT agent_id, role, content, timestamp, channel FROM conversations ORDER BY id")]
with memory.get_db() as live:
    if apply:
        dst = sqlite3.connect(SAFE); live.backup(dst); dst.close(); print("live brain backed up ->", SAFE)
    live_rows = [dict(r) for r in live.execute("SELECT agent_id, role, content, timestamp, channel FROM conversations ORDER BY id")]
    key = lambda r: (r["agent_id"], r["timestamp"], r["role"], r["content"])
    have = {key(r) for r in old}
    merged = old + [r for r in live_rows if key(r) not in have]
    merged.sort(key=lambda r: (r["agent_id"], r["timestamp"]))
    agents = sorted({r["agent_id"] for r in merged})
    for a in agents:
        rows = [r for r in merged if r["agent_id"] == a]
        n_live = sum(1 for r in live_rows if r["agent_id"] == a)
        print(f"{a:12s} live {n_live:3d} -> restored {len(rows):3d}  ({sum(1 for r in rows if r['channel']=='personal')} home, "
              f"{rows[0]['timestamp'][:10]} .. {rows[-1]['timestamp'][:10]})")
        if apply:
            live.execute("DELETE FROM conversations WHERE agent_id = ?", (a,))
            live.executemany("INSERT INTO conversations (agent_id, role, content, timestamp, channel) VALUES (?, ?, ?, ?, ?)",
                             [(r["agent_id"], r["role"], r["content"], r["timestamp"], r["channel"]) for r in rows])
    if apply:
        live.commit()
        print("total rows now:", live.execute("SELECT COUNT(*) FROM conversations").fetchone()[0])
print("DRY RUN -- add --apply" if not apply else "APPLIED")
