"""WHAT ACTUALLY HAPPENED -- the outcome log the learning system learns from (2026-09-24).

Barry: "build the learning system". Research (docs/reliability-research-2026-09-24.md + the learning
report): agents that learn from their own opinion of how they did get WORSE; agents that learn from
outcomes something real checked get better. So this module records only events an outside signal
produced -- never the agent's self-assessment:
  claim_caught / claim_fixed / claim_stuck   -- the claim net (claim_net.gaps) and its re-run
  number_caught / number_fixed / number_stuck -- the numbers check and its re-run
  readback_failed                             -- a write did not land (readback.py)
  tool_error                                  -- a tool returned an error
  approved / rejected                         -- Barry's own click on the approvals queue

Work only: home turns and Taliyah are never recorded (private). No message text of Barry's is
stored -- the details are the office's own check text. One JSONL per office in data/outcomes/.
The daily learning review (learning_review.py) shows unreviewed events to the agent, who decides
the lesson in their own words; nothing here writes a lesson.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime

import contextvars

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(_ROOT, "data", "outcomes")
PRIVATE = {"taliyah", "Taliyah"}
_lock = threading.Lock()
# Set True by main.chat for home / personal turns: nothing from a private turn is ever recorded,
# whichever module (tool dispatcher, nets) tries to record it.
private_turn: contextvars.ContextVar = contextvars.ContextVar("outcomes_private_turn", default=False)


def _path(office: str) -> str:
    return os.path.join(DIR, re.sub(r"[^A-Za-z0-9_-]", "_", office or "unknown") + ".jsonl")


def record(office: str, kind: str, detail: str, **extra) -> str | None:
    """Append one real outcome. Returns its id (E<ms>) or None when not recorded. Never raises."""
    try:
        if not office or office in PRIVATE or private_turn.get():
            return None
        eid = f"E{int(time.time() * 1000)}"
        row = {"id": eid, "ts": datetime.now().isoformat(timespec="seconds"), "office": office,
               "kind": kind, "detail": (detail or "")[:300], "reviewed": False}
        row.update({k: v for k, v in extra.items() if isinstance(v, (str, int, float, bool))})
        with _lock:
            os.makedirs(DIR, exist_ok=True)
            with open(_path(office), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        time.sleep(0.002)                          # ids stay unique within a burst
        return eid
    except Exception:                              # noqa: BLE001 -- logging must never break a turn
        return None


def load(office: str) -> list[dict]:
    try:
        with open(_path(office), encoding="utf-8") as fh:
            return [json.loads(l) for l in fh if l.strip()]
    except (OSError, ValueError):
        return []


def pending(office: str, limit: int = 12) -> list[dict]:
    return [r for r in load(office) if not r.get("reviewed")][-limit:]


def exists(office: str, ids) -> set:
    have = {r["id"] for r in load(office)}
    return {i for i in (ids or []) if i in have}


def mark_reviewed(office: str, ids) -> None:
    ids = set(ids or [])
    if not ids:
        return
    with _lock:
        rows = load(office)
        for r in rows:
            if r["id"] in ids:
                r["reviewed"] = True
        tmp = _path(office) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, _path(office))


def offices_with_pending() -> list[str]:
    out = []
    if not os.path.isdir(DIR):
        return out
    for f in sorted(os.listdir(DIR)):
        if f.endswith(".jsonl"):
            rows = []
            try:
                with open(os.path.join(DIR, f), encoding="utf-8") as fh:
                    rows = [json.loads(l) for l in fh if l.strip()]
            except (OSError, ValueError):
                pass
            if any(not r.get("reviewed") for r in rows) and rows:
                out.append(rows[0]["office"])
    return out
