"""WHO'S WORKING -- the office's live activity board (2026-09-26).

Barry, 2026-09-26: "I need to know whos working, so i dont interupt things. so make it so i know whos
doing what and when."

READ-ONLY VISIBILITY. Nothing here stops, queues or changes any work. It records every /api/chat turn
while it runs (who, what kind of work, since when) via ActivityMiddleware in main.py, plus anything that
calls begin()/end() itself (e.g. email renders), and reads the machine's other signals: the GPU render
flag, free RAM, and what is scheduled next.

PRIVACY: no message text is ever stored or shown -- only the seat and a work label. A caller can name its
work with an "activity" field in the /api/chat JSON (e.g. "writing this week's email"); otherwise the label
comes from the request's shape (task / brief / home / office).
"""
from __future__ import annotations

import ctypes
import datetime
import glob
import json
import os
import re
import threading
import time
import uuid

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA = os.path.join(_ROOT, "data")
_LOCK = threading.Lock()
_ACTIVE: dict[str, dict] = {}
_RECENT: list[dict] = []
MAX_RECENT = 12

_NAMES = {"cio": "Victor", "operations": "Priya", "business": "Amara", "legal": "Marcus",
          "marketing": "Derek", "creative": "Vivian", "movie": "Elliot", "engineer": "Sophie",
          "taliyah": "Taliyah", "ilnora": "Ilnora"}


def _now() -> float:
    return time.time()


def begin(who: str, what: str, kind: str = "task") -> str:
    tok = uuid.uuid4().hex[:10]
    with _LOCK:
        _ACTIVE[tok] = {"who": who, "what": what, "kind": kind, "since": _now()}
    return tok


def end(tok: str | None) -> None:
    if not tok:
        return
    with _LOCK:
        e = _ACTIVE.pop(tok, None)
        if e:
            e = dict(e, ended=_now())
            _RECENT.insert(0, e)
            del _RECENT[MAX_RECENT:]


def turn_in_flight(max_age_s: float = 45 * 60) -> str:
    """The agent turn (chat or task) running RIGHT NOW, as 'Who what', or '' (2026-10-10). Ilnora's video queue
    started a build 30 s after her turn hit the time ceiling, unloaded Bonsai under her forced-answer pass, and
    Barry saw "transmission failed". A build must wait for the turn. Entries older than max_age_s are ignored
    (a turn that never ended is a leak, not a reason to hold the card all night)."""
    with _LOCK:
        act = [e for e in _ACTIVE.values() if e.get("kind") in ("chat", "task") and _now() - e["since"] < max_age_s]
    act.sort(key=lambda x: x["since"])
    return f"{act[0]['who']} {act[0]['what']}" if act else ""


def label_for_chat(body: dict) -> tuple[str, str, str]:
    """(who, what, kind) for one /api/chat request -- never the message text."""
    aid = str(body.get("agent_id") or "?")
    who = _NAMES.get(aid, aid)
    if body.get("activity"):
        return who, str(body["activity"])[:80], "task"
    if body.get("task"):
        if body.get("brief_id"):
            return who, f"working brief #{body['brief_id']}", "task"
        return who, "office task", "task"
    if body.get("personal"):
        return who, "at home with Barry", "chat"
    return who, "talking with Barry", "chat"


def _free_ram_gb() -> float | None:
    try:
        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("a", ctypes.c_ulonglong), ("b", ctypes.c_ulonglong), ("c", ctypes.c_ulonglong),
                        ("d", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]
        m = MS(); m.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return round(m.ullAvailPhys / 1e9, 1)
    except Exception:
        return None


def _render() -> str | None:
    p = os.path.join(_DATA, "video_rendering.flag")
    if not os.path.exists(p):
        return None
    try:
        age = int((time.time() - os.path.getmtime(p)) / 60)
        tag = open(p, encoding="utf-8", errors="ignore").read().strip()[:60]
    except OSError:
        age, tag = 0, ""
    return f"GPU render running ({tag or 'render'}), {age} min"


def _next_up() -> list[str]:
    out = []
    try:
        import email_cadence
        s = email_cadence.upcoming_slots()
        if s:
            out.append(f"Derek's next email slot: {s[0][0]:%a %b %d %I:%M %p}".replace(" 0", " "))
    except Exception:
        pass
    return out


def _ago(t: float) -> str:
    s = int(_now() - t)
    return f"{s // 60} min" if s >= 60 else f"{s} s"


def busy_line() -> dict:
    """What the office is doing RIGHT NOW, cheap enough for a 45-second probe (2026-10-07, Barry: "make the watchdog
    know when a video is being made or something. dont just wait for it to fail, make it know whats going on").
    "busy" is for the log (with times); "key" is the same without times, so the watchdog logs only changes."""
    with _LOCK:
        act = sorted(_ACTIVE.values(), key=lambda x: x["since"])
    busy = [f"{e['who']} {e['what']} ({_ago(e['since'])})" for e in act[:3]]
    key = [f"{e['who']} {e['what']}" for e in act[:3]]
    if len(act) > 3:
        busy.append("+ more")
        key.append("+ more")
    for flag, label in (("reel_building.flag", "building"), ("video_rendering.flag", "GPU render")):
        f = os.path.join(_DATA, flag)
        if os.path.exists(f):
            try:
                tag = open(f, encoding="utf-8", errors="ignore").read().strip()[:60]
                age = int((_now() - os.path.getmtime(f)) / 60)
            except OSError:
                tag, age = "", 0
            busy.append(f"{label} '{tag}' {age} min" if tag else f"{label} {age} min")
            key.append(f"{label} '{tag}'" if tag else label)
    return {"busy": " · ".join(busy) or "quiet", "key": " · ".join(key) or "quiet"}


def snapshot() -> dict:
    with _LOCK:
        active = [dict(e, running_for=_ago(e["since"]),
                       started=datetime.datetime.fromtimestamp(e["since"]).strftime("%I:%M %p").lstrip("0"))
                  for e in sorted(_ACTIVE.values(), key=lambda x: x["since"])]
        recent = [{"who": e["who"], "what": e["what"],
                   "finished": datetime.datetime.fromtimestamp(e["ended"]).strftime("%I:%M %p").lstrip("0"),
                   "took": f"{int((e['ended'] - e['since']) // 60)} min {int((e['ended'] - e['since']) % 60)} s"}
                  for e in _RECENT]
    render = _render()
    busy_bonsai = [e for e in active if e["kind"] in ("chat", "task")]
    heavy = bool(render)
    parts = [f"{e['who']} ({e['what']})" for e in active[:3]] + (["+ more"] if len(active) > 3 else [])
    if render:
        parts.append(render)
    headline = "BUSY -- " + " · ".join(parts) if parts else "QUIET -- nobody is working"
    return {"headline": headline, "active": active, "recent": recent, "render": render,
            "free_ram_gb": _free_ram_gb(), "next_up": _next_up(),
            "note": ("Bonsai answers ONE turn at a time: a message sent now waits behind "
                     f"{len(busy_bonsai)} running turn(s)." if busy_bonsai else "Bonsai is free.")}


class ActivityMiddleware:
    """Pure ASGI: records each POST /api/chat while it runs. Reads the body once and replays it."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("method") != "POST" or scope.get("path") != "/api/chat":
            return await self.app(scope, receive, send)
        chunks, more = [], True
        while more:
            msg = await receive()
            chunks.append(msg.get("body", b""))
            more = msg.get("more_body", False)
        body = b"".join(chunks)
        tok = None
        try:
            who, what, kind = label_for_chat(json.loads(body or b"{}"))
            tok = begin(who, what, kind)
        except Exception:
            pass
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()
        try:
            await self.app(scope, replay, send)
        finally:
            end(tok)
