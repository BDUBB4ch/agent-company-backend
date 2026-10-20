"""
Cheap safety net for brain.db -- it's the entire memory of this office
(every seeded fact, conversation, approval, custom hire), lives as one
SQLite file, and had zero backup until now. On every backend startup,
copies the current brain.db into data/backups/ with a timestamp, then
prunes down to the newest KEEP_LAST copies so this doesn't grow forever.

Uses SQLite's own backup API (not a plain file copy) so a backup taken
while the file could theoretically be mid-write never produces a corrupt
copy -- safe to call at any time, not just at startup.
"""
import os
import sqlite3
import datetime
import glob

from config import DB_PATH, DATA_DIR

BACKUP_DIR = os.path.join(DATA_DIR, "backups")
KEEP_LAST = 14  # ~2 weeks of daily-ish backend restarts, adjust freely


def backup_now() -> str | None:
    """Returns the backup file path, or None if there's no brain.db yet
    (e.g. a completely fresh install that hasn't run once)."""
    if not os.path.isfile(DB_PATH):
        return None

    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"brain_{timestamp}.db")

    source = sqlite3.connect(DB_PATH)
    dest = sqlite3.connect(backup_path)
    with dest:
        source.backup(dest)
    dest.close()
    source.close()

    _prune_old_backups()
    return backup_path


def _prune_old_backups():
    backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "brain_*.db")))
    for old_backup in backups[:-KEEP_LAST]:
        try:
            os.remove(old_backup)
        except OSError:
            pass  # not worth failing startup over a cleanup step
