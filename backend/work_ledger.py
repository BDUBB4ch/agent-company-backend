"""WORK LEDGER -- what each seat wrote, planned and finished, kept by the office (2026-10-12).

Barry: "she needs to remember the shit she writes and the videos she has planned, so give my agents that memory
thing i gave you" (the agent-memory plugin). Its idea, adapted as plain code (nothing installed, no outside calls):
  1. WATCH  -- after every successful tool call the office writes one short observation (what was done, to what).
  2. KEEP   -- one line per observation in data/ledger/<office>.jsonl; the agent never has to "remember to save".
  3. SHOW   -- a small digest (open plans, what is in progress, what was finished lately) rides at the END of each
              work turn, so the agent starts every turn knowing its own recent work.
  4. SEARCH -- the full lines stay on disk; the agent asks for older ones by word (Ilnora: video_draft "ledger" / "past").
Only facts the office saw happen are recorded -- never an agent's feelings or its opinion of itself. Work turns only:
home / personal turns and Taliyah are never recorded (same switch outcomes.py uses). Word-for-word text of Barry's
messages is not stored here; his planned asks come in as plan lines he can see.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(_ROOT, "data", "ledger")
_lock = threading.Lock()
PRIVATE = {"taliyah", "Taliyah"}
DIGEST_CHARS = 2400
KEEP_LINES = 400                      # per seat; older lines are folded away at 2x this size


def _path(office: str) -> str:
    return os.path.join(DIR, re.sub(r"[^A-Za-z0-9_-]", "_", office or "unknown") + ".jsonl")


def _private() -> bool:
    try:
        import outcomes
        return bool(outcomes.private_turn.get())
    except Exception:                                   # noqa: BLE001
        return False


def note(office: str, kind: str, title: str, text: str = "", **extra) -> None:
    """Append one observation. kinds: plan | started | wrote | checked | sent | made | desk | done | note."""
    if not office or office in PRIVATE or _private():
        return
    row = {"t": round(time.time(), 1), "kind": kind, "title": (title or "")[:120], "text": (text or "")[:400]}
    row.update({k: v for k, v in extra.items() if v not in (None, "")})
    with _lock:
        os.makedirs(DIR, exist_ok=True)
        with open(_path(office), "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load(office: str) -> list[dict]:
    try:
        with open(_path(office), encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]
    except FileNotFoundError:
        return []
    except Exception:                                   # noqa: BLE001
        return []


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _day(t: float) -> str:
    return datetime.fromtimestamp(t).strftime("%b %d")


# --- what the office saw, turned into one line ------------------------------------------------------------------
def observe(office: str, tool: str, args: dict, result) -> None:
    """Called by the tool dispatcher after a call. Never raises, never blocks the tool."""
    try:
        if not isinstance(args, dict) or (isinstance(result, dict) and result.get("error")):
            return
        if tool == "video_draft":
            act = str(args.get("action") or "").lower()
            d = result if isinstance(result, dict) else {}
            title = str(args.get("title") or d.get("title") or "")
            if act == "start":
                note(office, "started", title, f'{args.get("format", "")} draft begun' + (f' (redo of {args["redo_of"]})' if args.get("redo_of") else ""))
            elif act == "add_parts":
                parts = args.get("parts") or []
                first = str((parts[0] or {}).get("say", ""))[:160] if parts and isinstance(parts[0], dict) else ""
                note(office, "wrote", title or "current draft", f'{len(parts)} part(s) written; first: "{first}"', words=d.get("words"))
            elif act == "send":
                note(office, "sent", title or "current draft", "checked and queued to build", words=d.get("words"))
            elif act == "discard":
                note(office, "note", title or "current draft", "draft discarded")
        elif tool == "make_video":
            note(office, "sent", str(args.get("title") or ""), f'{args.get("format", "")} queued to build via make_video')
        elif tool == "send_file_to_barry":
            note(office, "desk", str(args.get("filename") or args.get("name") or "file"), "put on his desk")
        elif tool == "delegate_to":
            note(office, "note", str(args.get("agent") or args.get("to") or ""), "handed work: " + str(args.get("task") or args.get("message") or "")[:200])
    except Exception:                                   # noqa: BLE001
        pass


# --- the digest the agent starts a turn with --------------------------------------------------------------------
def _ilnora_state() -> list[str]:
    """Ground truth for her videos: the queue and the draft on disk, not just what the ledger saw."""
    out: list[str] = []
    try:
        import video_queue
        import video_tool
        jobs = video_queue.made_jobs()
        done = [j for j in jobs if j.get("status") == "done"]
        waiting = [j for j in jobs if j.get("status") not in ("done", "replaced", "failed")]
        if done:
            out.append("MADE (on his desk): " + "; ".join(
                f'{j["pkg"].get("title", "")} [{j["pkg"].get("format", "")}]' for j in done[-12:]))
        if waiting:
            out.append("WRITTEN, NOT BUILT YET: " + "; ".join(
                f'{j["pkg"].get("title", "")} [{j.get("status")}]' for j in waiting[-8:]))
        d = video_tool.load_draft("ilnora")
        if d and d.get("title"):
            out.append(f'YOUR OPEN DRAFT: "{d["title"]}" ({d.get("format")}), {len(d.get("parts") or [])} part(s) saved'
                       + (f' -- a redo of "{d["redo_of"]}"' if d.get("redo_of") else ""))
    except Exception:                                   # noqa: BLE001
        pass
    return out


def digest(office: str) -> str:
    """The short block for the end of a work turn. Empty when there is nothing to remember yet."""
    if not office or office in PRIVATE:
        return ""
    rows = load(office)
    plans = [r for r in rows if r["kind"] == "plan"]
    closed = {_norm(r["title"]) for r in rows if r["kind"] in ("sent", "made", "done")}
    open_plans = []
    seen = set()
    for r in reversed(plans):
        k = _norm(r["title"])
        if k in seen:
            continue
        seen.add(k)
        if k in closed or any(k and (k in c or c in k) and min(len(k), len(c)) >= 8 for c in closed):
            continue
        open_plans.append(r)
    lines: list[str] = []
    if office.lower() == "ilnora":
        lines += _ilnora_state()
    if open_plans:
        lines.append("PLANNED, NOT DONE: " + " | ".join(f'{r["title"]} ({_day(r["t"])}: {r["text"][:110]})' for r in reversed(open_plans[:8])))
    recent = [r for r in rows if r["kind"] != "plan"][-10:]
    if recent:
        lines.append("RECENT WORK: " + " | ".join(f'{_day(r["t"])} {r["kind"]} {r["title"][:50]}: {r["text"][:90]}' for r in recent))
    if not lines:
        return ""
    body = "\n".join(lines)[:DIGEST_CHARS]
    tail = ('Older entries: ' + ('video_draft action "ledger" (text = a word to search for), or "past" (title) to read a finished script word for word.'
            if office.lower() == "ilnora" else "ask Barry or look in your desk files."))
    return ("\n\n--- YOUR WORK LEDGER (the office kept these from what you did; plans are what you recorded) ---\n" + body + "\n" + tail)


def search(office: str, query: str, limit: int = 15) -> list[dict]:
    toks = [t for t in _norm(query).split() if len(t) > 2]
    rows = load(office)
    if not toks:
        return rows[-limit:]
    hit = [r for r in rows if all(t in _norm(r["title"] + " " + r["text"]) for t in toks)]
    return hit[-limit:]


def fold_old(office: str) -> None:
    """Keep the file small: past KEEP_LINES*2 lines, keep plans and the newest KEEP_LINES."""
    rows = load(office)
    if len(rows) <= KEEP_LINES * 2:
        return
    keep = [r for r in rows[:-KEEP_LINES] if r["kind"] == "plan"] + rows[-KEEP_LINES:]
    with _lock:
        with open(_path(office), "w", encoding="utf-8") as f:
            for r in keep:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
