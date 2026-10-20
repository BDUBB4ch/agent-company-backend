"""
Mirrors everything printed to stdout/stderr (including unhandled
tracebacks) into a real file, data/backend.log, in addition to the normal
console -- so a backend error is always somewhere you can actually open,
read, and copy-paste, not just whatever happened to still be visible in
whichever terminal window (or hidden background process) it was running
in. Call setup() as the very first thing main.py does, before any other
import can print anything.
"""
import sys
import os
import re
import datetime
from config import DATA_DIR

# uvicorn colors its console output with ANSI escape codes -- harmless in a
# real terminal, but they'd show up as raw control-character junk mixed
# into text Barry copies out of the Errors tab, so strip them when reading
# back (the log FILE still contains them, only the served text is cleaned).
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

LOG_PATH = os.path.join(DATA_DIR, "backend.log")
MAX_LOG_BYTES = 5 * 1024 * 1024  # rotate once the log passes ~5MB rather than growing forever


class _Tee:
    """Writes to both the original stream (so the console still works
    exactly as before) and the log file."""

    def __init__(self, stream, log_file):
        self._stream = stream
        self._log_file = log_file

    def write(self, data):
        self._stream.write(data)
        self._log_file.write(data)
        self._log_file.flush()  # errors matter immediately, not on buffer flush

    def flush(self):
        self._stream.flush()
        self._log_file.flush()

    def isatty(self):
        return self._stream.isatty()


def _rotate_if_needed():
    if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > MAX_LOG_BYTES:
        old_path = LOG_PATH + ".old"
        if os.path.exists(old_path):
            os.remove(old_path)
        os.rename(LOG_PATH, old_path)


def setup():
    os.makedirs(DATA_DIR, exist_ok=True)
    _rotate_if_needed()
    log_file = open(LOG_PATH, "a", encoding="utf-8")
    log_file.write(f"\n--- backend started {datetime.datetime.now().isoformat()} ---\n")
    log_file.flush()
    sys.stdout = _Tee(sys.stdout, log_file)
    sys.stderr = _Tee(sys.stderr, log_file)


def read_tail(max_chars: int = 20000) -> str:
    """Last max_chars of the log, across both the current file and the one
    rotated-out .old file if the current one is still short -- so a fresh
    restart doesn't immediately lose visibility into the error that
    happened right before it."""
    chunks = []
    for path in (LOG_PATH + ".old", LOG_PATH):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                chunks.append(f.read())
    combined = _ANSI_RE.sub("", "\n".join(chunks))
    return combined[-max_chars:] if combined else "(no log entries yet)"
