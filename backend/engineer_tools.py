"""SOPHIE, FULLY CAPABLE (Barry, 2026-09-06: "i need Sophie to be able to do
everything needed, to build anything i need" / "she needs to be fully
capable, like i have been telling you from the beginning").

Before this she could read two folders, snippet-edit an existing file, and
nothing else: no creating a file, no reading the dashboard, no running a
test, no installing a package, no restart, no updates. This module adds the
missing hands, under the rules he already set (2026-09-02): simple things
she does herself and tells him; bigger things wait in his queue; undo is
his word; the safety net (codefix / watch / memory / dispatch / config) is
never touched unattended.

  search_project(pattern, root)   grep across the build (read-only)
  run_command(command)            SAFE commands run now (tests, preflight,
                                  py_compile, node --check, git status/log/
                                  diff, pip show/list, dir). Anything else --
                                  including `pip install` -- is QUEUED as an
                                  `engineer_task` approval and runs when Barry
                                  approves; output lands on the row + her journal.
  restart_backend()               the house restart (process exits, watchdog
                                  revives within ~45s). Refused mid-render.
  check_updates(action)           status / check / apply:<item>; apply queues
                                  for Barry (his standing rule: he chooses
                                  when to pull an update).
  run_approved(approval_id)       the approve endpoint calls this for
                                  `engineer_task` rows.

Whole-file writes live in codefix.propose_write (same backup/undo/preflight
machinery as snippet fixes -- one door, one journal, one undo).
"""
from __future__ import annotations

import datetime
import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time

import memory
import read_project_file
from config import COMFY_DIR, COMFY_PYTHON

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DASH = os.path.abspath(os.path.join(_ROOT, "..", "AgentDashboard"))
_DESKTOP = os.path.abspath(os.path.join(_ROOT, ".."))
ROOTS = {"backend": _ROOT, "dashboard": _DASH, "comfy": COMFY_DIR}
_MARKER = "===ENGINEER-TASK==="
_OUTPUT_CAP = 8_000
_PIP_DENY = {"torch", "torchvision", "torchaudio", "pytorch-triton-rocm", "triton"}
_SKIP_DIRS = {"venv", ".git", "__pycache__", "node_modules", "models", "output", "input",
              "_done", "_failed", "codefix_backups", "script_wip_backups"}

# Commands that read, test or verify and change nothing -- these run at once.
# Everything else is a change and goes through Barry.
_SAFE = [
    # functional_audit + tool_audit added 2026-09-28 (Barry: she is "the
    # custodian of it all"): both read and test only -- one uncounted chat turn
    # and harmless refused write probes; GPU/send/restart tools are gated off.
    r"^python(?:\.exe)? scripts[\\/](?:preflight_check|office_health|test_[\w\-]+|functional_audit_2026_09_07|tool_audit_2026_09_17)\.py(?:\s.*)?$",
    r"^python(?:\.exe)? -m py_compile .+$",
    r"^python(?:\.exe)? -m pip (?:show|list|check|freeze)(?:\s.*)?$",
    r"^node --check .+$",
    r"^git (?:status|log|diff|show|branch|remote)(?:\s.*)?$",
    r"^(?:dir|ls|type|cat|findstr|where|tree)(?:\s.*)?$",
    r"^schtasks /query(?:\s.*)?$",
    r"^winget (?:list|show|search)(?:\s.*)?$",
    r"^(?:where|Get-Process|tasklist|reg query)(?:\s.*)?$",
    # netstat (2026-09-28, Barry: "yes"): read-only view of what is listening
    # and on which address -- the "is anything exposed" question, answered.
    r"^netstat(?:\s+-[a-z]+)*(?:\s+-p\s+(?:tcp|udp))?$",
]
_SAFE_RE = [re.compile(p, re.I) for p in _SAFE]


def _log(line: str) -> None:
    try:
        with open(os.path.join(_ROOT, "data", "engineer_tasks.log"), "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now(datetime.UTC).isoformat()} {line}\n")
    except OSError:
        pass


# --------------------------------------------------------------- search ---
def search_project(pattern: str, root: str = "backend", glob: str = "", max_hits: int = 60) -> dict:
    """Regex search over the build's text files. Read-only."""
    base = ROOTS.get((root or "backend").lower()) or root
    base = os.path.abspath(base)
    if not any(base == r or base.startswith(r + os.sep) for r in ROOTS.values()):
        return {"error": f"root must be one of {sorted(ROOTS)} or a path inside them"}
    if not os.path.isdir(base):
        return {"error": f"not a directory: {base}"}
    try:
        rx = re.compile(pattern, re.I)
    except re.error as e:
        return {"error": f"bad regex: {e}"}
    exts = {".py", ".js", ".html", ".css", ".md", ".json", ".txt", ".bat", ".ps1", ".yaml", ".yml"}
    hits, scanned = [], 0
    for dirpath, dirnames, files in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for fn in files:
            if os.path.splitext(fn)[1].lower() not in exts:
                continue
            if glob and not fnmatch.fnmatch(fn, glob):
                continue
            if read_project_file.is_secret_path(fn):      # never search inside keys/tokens (2026-09-28)
                continue
            p = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(p) > 3_000_000:
                    continue
                scanned += 1
                with open(p, encoding="utf-8", errors="replace") as f:
                    for n, line in enumerate(f, 1):
                        if rx.search(line):
                            hits.append({"file": os.path.relpath(p, base), "line": n, "text": line.rstrip()[:200]})
                            if len(hits) >= max_hits:
                                return {"root": base, "files_scanned": scanned, "hits": hits, "truncated": True}
            except OSError:
                continue
    return {"root": base, "files_scanned": scanned, "hits": hits, "truncated": False}


# ------------------------------------------------------------- commands ---
def _tokens(command: str) -> list[str]:
    toks = shlex.split(command, posix=False)
    return [t[1:-1] if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'" else t for t in toks]


def _resolve_exe(tok: str, cwd: str) -> str:
    low = tok.lower()
    if low in ("python", "python.exe", "py"):
        return COMFY_PYTHON if cwd.lower().startswith(COMFY_DIR.lower()) else sys.executable
    return tok


def _cwd_for(cwd: str | None) -> tuple[str | None, str | None]:
    if not cwd:
        return _ROOT, None
    key = cwd.lower()
    if key in ROOTS:
        return ROOTS[key], None
    p = os.path.abspath(cwd)
    if not any(p == r or p.startswith(r + os.sep) for r in ROOTS.values()):
        return None, "cwd must be inside the build (backend / dashboard / comfy)"
    if not os.path.isdir(p):
        return None, f"no such directory: {p}"
    return p, None


def _execute(command: str, cwd: str, timeout: int = 300) -> dict:
    try:
        toks = _tokens(command)
    except ValueError as e:
        return {"status": "failed", "why": f"could not parse the command: {e}"}
    if not toks:
        return {"status": "failed", "why": "empty command"}
    toks[0] = _resolve_exe(toks[0], cwd)
    if toks[0].lower() in ("dir", "type", "tree", "findstr", "where"):
        toks = ["cmd", "/c"] + toks
    elif toks[0].lower() in ("ls", "cat"):
        toks = ["powershell", "-NoProfile", "-Command", " ".join(toks)]
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    t0 = time.time()
    try:
        r = subprocess.run(toks, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace", env=env)
        out = (r.stdout or "") + (r.stderr or "")
        rc = r.returncode
    except subprocess.TimeoutExpired:
        return {"status": "failed", "why": f"timed out after {timeout}s", "command": command}
    except OSError as e:
        return {"status": "failed", "why": f"could not run it: {e}", "command": command}
    truncated = len(out) > _OUTPUT_CAP
    if truncated:
        out = out[:_OUTPUT_CAP // 2] + "\n...[output trimmed]...\n" + out[-_OUTPUT_CAP // 2:]
    return {"status": "ok" if rc == 0 else "nonzero_exit", "exit_code": rc,
            "seconds": round(time.time() - t0, 1), "output": out, "truncated": truncated,
            "command": command, "cwd": cwd}


def is_safe_command(command: str) -> bool:
    c = " ".join((command or "").strip().split())
    return any(rx.match(c) for rx in _SAFE_RE)


def _pip_install_check(command: str) -> str | None:
    """Refuse pip installs that would swap the ROCm torch or point at odd indexes."""
    if not re.match(r"^python(?:\.exe)?\s+-m\s+pip\s+install\b|^pip\s+install\b", command, re.I):
        return None
    if re.search(r"--index-url|--extra-index-url|-i\s|--find-links|-f\s|--pre\b|-e\s|git\+", command, re.I):
        return "pip install with a custom index / editable / VCS source is refused -- Barry and Claude only."
    for tok in command.split()[3:]:
        base = re.split(r"[=<>!~\[]", tok, 1)[0].lower()
        if base in _PIP_DENY:
            return f"{base} is the hand-installed ROCm build -- never reinstalled from here."
    return None


def run_command(command: str, cwd: str | None = None, why: str = "") -> dict:
    """Safe commands run now; anything else is queued for Barry."""
    command = (command or "").strip()
    if not command:
        return {"status": "refused", "why": "empty command"}
    if any(ch in command for ch in ("&&", "||", "|", ";", ">", "<", "`", "$(")):
        return {"status": "refused", "why": "one plain command at a time -- no pipes, chains or redirects. "
                                            "Read files with read_project_file instead of cat|grep."}
    wd, err = _cwd_for(cwd)
    if err:
        return {"status": "refused", "why": err}
    # NO COMMAND READS A SECRET (2026-09-28). `type .env`, `cat .env` and
    # `findstr /s KEY *` were all on the safe list and would print the keys.
    # Refused outright (not queued): no approval should ever print them either.
    try:
        _toks = _tokens(command)
    except ValueError:
        _toks = command.split()
    if any(read_project_file.is_secret_path(t) for t in _toks):
        return {"status": "refused", "why": "that names a file holding keys or tokens -- never read or printed "
                                            "(Barry's rule). system_health says whether a key is set."}
    if _toks and _toks[0].lower() in ("type", "cat", "findstr") and (
            any(ch in command for ch in "*?") or re.search(r"(?i)\s/s\b", command)):
        return {"status": "refused", "why": "no wildcard or recursive type/cat/findstr -- it can sweep secret files. "
                                            "Use search_project (it skips them) or read_project_file."}
    bad = _pip_install_check(command)
    if bad:
        return {"status": "refused", "why": bad}
    if is_safe_command(command):
        res = _execute(command, wd)
        _log(f"ran (safe): {command} -> {res.get('status')}")
        return res
    if re.match(r"^pip\s+install\b", command, re.I):
        command = "python -m " + command
    payload = json.dumps({"kind": "command", "command": command, "cwd": wd})
    content = (
        f"ENGINEER TASK -- run a command\n\n"
        f"{(why or 'Sophie asked to run this.').strip()}\n\n"
        f"COMMAND: {command}\nIN: {wd}\n\n"
        f"When you approve, the office runs it and the output goes back to Sophie.\n\n"
        f"{_MARKER}\n{payload}"
    )
    aid = memory.queue_for_approval("engineer", "engineer_task", content)
    _log(f"queued #{aid}: {command}")
    _refresh_journal()
    return {"status": "queued", "approval_id": aid,
            "note": ("This command CHANGES something (or is not on the safe list), so it is "
                     "waiting in Barry's Pending Review -- it has NOT run. Tell him what it "
                     "does and why; when he approves, the output lands in your fix journal "
                     f"(list_code_fixes) under task #{aid}.")}


# -------------------------------------------------------------- restart ---
_RESTART_PENDING = threading.Event()


def restart_backend(reason: str = "") -> dict:
    """The house restart, done safely (rebuilt 2026-10-10). The old version exited 3 s after the call -- in the
    MIDDLE of Sophie's own turn, so her reply never reached Barry -- with no preflight and no check for a building
    video. On 2026-10-10 she avoided it, ran out of time reading files, and her forced answer said "Restarted the
    backend" when nothing had restarted. Now: refuse under a render or a building video, refuse if preflight fails
    (the new code would not start), otherwise wait until every turn -- hers included -- has finished (max 15 min)
    and exit; the watchdog revives the backend with the current code in under a minute (data/watchdog.log)."""
    import activity
    try:
        import comfy_image
        if comfy_image.render_in_progress():
            return {"status": "refused", "why": "a render holds the GPU -- a restart would kill it "
                                                "(the 2026-08-30 lesson). Wait for it to finish."}
    except Exception:  # noqa: BLE001
        pass
    try:
        import video_queue
        building = [j.get("pkg", {}).get("title") for j in video_queue._jobs() if j.get("status") == "building"]
        if building:
            return {"status": "refused", "why": f"a video is building ({building[0]!r}) -- a restart would kill it. "
                                                "Wait for it, or hold builds with office_ops first."}
    except Exception:  # noqa: BLE001
        pass
    if _RESTART_PENDING.is_set():
        return {"status": "scheduled", "note": "a restart is already waiting for the current turn(s) to finish"}
    pf = subprocess.run([sys.executable, os.path.join(_ROOT, "scripts", "preflight_check.py")], cwd=_ROOT,
                        capture_output=True, text=True, timeout=300)
    if pf.returncode != 0:
        return {"status": "refused", "why": "preflight FAILED -- the new code would not start. Fix this first.",
                "preflight_tail": (pf.stdout or "")[-1500:]}
    _log(f"restart scheduled: {reason}")

    def _when_quiet():
        t0 = time.time()
        time.sleep(5)
        while time.time() - t0 < 15 * 60:
            try:
                busy = bool(activity.turn_in_flight())
            except Exception:  # noqa: BLE001
                busy = False
            if not busy:
                _log("restart: every turn finished -- exiting, the watchdog revives the backend")
                time.sleep(2)
                os._exit(0)
            time.sleep(5)
        _log("restart CANCELLED: a turn was still running after 15 min")
        _RESTART_PENDING.clear()

    _RESTART_PENDING.set()
    threading.Thread(target=_when_quiet, daemon=True).start()
    return {"status": "scheduled", "preflight": "ALL CLEAR",
            "note": ("Preflight passed. The backend restarts as soon as your reply (and any other turn) has "
                     "finished; the watchdog brings it back with the current code in under a minute. Tell Barry "
                     "it is restarting right after this reply. It is NOT verified yet: after it is back, check "
                     "data/watchdog.log for the restart line and the thing you fixed.")}


# -------------------------------------------------------------- updates ---
def check_updates(action: str = "status") -> dict:
    import updates
    action = (action or "status").strip()
    if action == "check":
        if memory.is_offline_mode():
            return {"status": "refused", "why": "Offline Mode is on -- no update check without the internet."}
        return _slim(updates.check())
    if action.startswith("apply:"):
        item_id = action.split(":", 1)[1].strip()
        item = next((i for i in updates.result().get("items", []) if i["id"] == item_id), None)
        if not item:
            return {"status": "refused", "why": f"no such item {item_id!r}; run action='status' for the ids"}
        if not item.get("can_apply"):
            return {"status": "refused", "why": item.get("how") or "manual item"}
        payload = json.dumps({"kind": "update", "item": item_id})
        content = (f"ENGINEER TASK -- apply an update\n\n{item['name']}: {item.get('current')} -> "
                   f"{item.get('latest')}\n\nHOW: {item.get('how')}\n{item.get('note') or ''}\n\n"
                   f"{_MARKER}\n{payload}")
        aid = memory.queue_for_approval("engineer", "engineer_task", content)
        _refresh_journal()
        return {"status": "queued", "approval_id": aid,
                "note": "Updates only run on Barry's click (his rule). It is in Pending Review; nothing has changed."}
    return _slim(updates.result())


def _slim(st: dict) -> dict:
    return {"checked_at": st.get("checked_at"), "online": st.get("online"), "error": st.get("error"),
            "items": [{k: i.get(k) for k in ("id", "name", "current", "latest", "update_available",
                                              "can_apply", "how", "note", "error")}
                      for i in st.get("items", [])],
            "recent_jobs": [{"item": j["item"], "status": j["status"], "last_lines": j["log"][-3:]}
                            for j in st.get("jobs", [])]}


# ------------------------------------------------------------- approval ---
def run_approved(approval_id: int) -> dict:
    """Called from the approve endpoint for `engineer_task` rows."""
    entry = memory.get_output_by_id(approval_id)
    if not entry or entry.get("action_type") != "engineer_task":
        return {"status": "failed", "why": "not an engineer task"}
    content = entry.get("content", "")
    if _MARKER not in content:
        return {"status": "failed", "why": "task payload missing"}
    try:
        payload = json.loads(content.split(_MARKER, 1)[1].strip())
    except ValueError as e:
        return {"status": "failed", "why": f"payload unreadable: {e}"}
    if entry.get("dispatched_at"):
        return {"status": "refused", "why": "already ran"}
    kind = payload.get("kind")
    if kind == "command":
        res = _execute(payload.get("command", ""), payload.get("cwd") or _ROOT, timeout=900)
    elif kind == "update":
        import updates
        res = updates.apply(payload.get("item", ""))
    elif kind == "elevated":                          # admin task (2026-10-10): his click = the UAC prompt
        import engineer_ops
        res = engineer_ops.run_elevated(payload.get("script", ""), payload.get("log", ""))
    else:
        res = {"status": "failed", "why": f"unknown task kind {kind!r}"}
    _record(approval_id, res)
    _log(f"approved #{approval_id} {kind}: {res.get('status')}")
    _refresh_journal()
    return res


def _record(approval_id: int, res: dict) -> None:
    with memory.get_db() as conn:
        conn.execute(
            "UPDATE approvals SET dispatch_status=?, dispatch_response=?, dispatched_at=? WHERE id=?",
            (res.get("status", "?"), json.dumps(res)[:6000], datetime.datetime.now(datetime.UTC).isoformat(),
             approval_id))


def task_rows(limit: int = 20) -> list[dict]:
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT id, status, dispatch_status, dispatch_response, created_at, decided_at, "
            "substr(content, 1, 600) AS head FROM approvals WHERE action_type='engineer_task' "
            "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        head = (d.pop("head") or "").split(_MARKER)[0]
        d["title"] = next((ln for ln in head.splitlines() if ln.startswith(("COMMAND:", "ENGINEER TASK"))), "")[:160]
        try:
            resp = json.loads(d.get("dispatch_response") or "{}")
            d["output"] = (resp.get("output") or resp.get("why") or resp.get("note") or "")[:1500]
        except ValueError:
            d["output"] = ""
        d.pop("dispatch_response", None)
        out.append(d)
    return out


def _refresh_journal() -> None:
    try:
        import codefix
        codefix.refresh_journal()
    except Exception as e:  # noqa: BLE001
        _log(f"journal refresh failed: {e}")
