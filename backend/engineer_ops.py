"""Sophie's hands on the office's moving parts, and the admin door (2026-10-10).

Barry: "tools to fix as well. and ability, not just knowledge" / "she needs tools that suit her build" /
"she needs to be able to do stuff, major stuff, but only with my permission."

office_ops  -- the video queue and drafts, the stack watchdog, the card, Bonsai's timings. Reads are free; the few
               writes are reversible and logged (pause/resume/requeue a job, hold/release the builds, archive a stuck
               draft, relaunch the supervisor). Nothing here deletes, posts or spends.
propose_admin_task -- machine-wide changes need a UAC prompt only Barry can click. She writes the elevated
               PowerShell; it lands on his pending board with WHAT / WHY / RISK + UNDO; his approve runs it under the
               prompt (engineer_tools.run_approved, kind "elevated") and the transcript lands in data/admin_tasks/.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import time

import memory

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DATA = os.path.join(_ROOT, "data")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_ADMIN_DIR = os.path.join(_ROOT, "scripts", "admin")
_ADMIN_LOG_DIR = os.path.join(_DATA, "admin_tasks")
_LOG = os.path.join(_DATA, "engineer_ops.log")


def _log(msg: str) -> None:
    try:
        with open(_LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}\n")
    except OSError:
        pass


def _tail(path: str, n: int = 40) -> list[str]:
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            return fh.read().splitlines()[-n:]
    except OSError:
        return []


# ---------------------------------------------------------------- office_ops
def office_ops(a: dict) -> dict:
    import video_queue
    import video_tool
    a = a if isinstance(a, dict) else {}
    action = str(a.get("action") or "").strip()
    if action == "video_queue":
        jobs = []
        for j in video_queue._jobs():
            row = {k: j.get(k) for k in ("status", "queued", "started", "finished", "minutes", "estimate_min", "folder_copy")}
            row.update(title=j.get("pkg", {}).get("title"), format=j.get("pkg", {}).get("format"),
                       parts=len(j.get("pkg", {}).get("scenes") or []))
            jobs.append(row)
        jobs.sort(key=lambda j: str(j.get("queued") or ""), reverse=True)
        drafts = {}
        if os.path.isdir(video_tool.DRAFT_DIR):
            for f in os.listdir(video_tool.DRAFT_DIR):
                if f.startswith("draft_") and f.endswith(".json") and f.count("_") == 1:
                    agent = f[6:-5]
                    d = video_tool.load_draft(agent)
                    if d:
                        st = video_tool.draft_status(d)
                        st["updated_min_ago"] = int((time.time() - float(d.get("updated") or 0)) / 60)
                        drafts[agent] = st
        hold = video_queue.held_until()
        return {"in_window": video_queue.in_window(), "minutes_left_in_window": round(video_queue.minutes_left()),
                "builds_held_for_min": max(0, int((hold - time.time()) / 60)) if hold > time.time() else 0,
                "jobs": jobs[:20], "drafts": drafts}
    if action == "video_events":
        hours = float(a.get("hours") or 6)
        since = (datetime.datetime.now() - datetime.timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        ev = [ln for ln in _tail(os.path.join(_DATA, "bonsai_events.log"), 400) if ln[:19] >= since]
        build = [ln for ln in _tail(os.path.join(_DATA, "reels", "make_video.log"), 200) if ln[:19] >= since]
        qlog = [ln for ln in _tail(os.path.join(_DATA, "video_queue", "queue.log"), 200) if ln[:19] >= since]
        return {"since": since, "bonsai_events": ev[-60:], "builder_log": build[-40:], "queue_log": qlog[-30:],
                "read_this_way": "TIME CEILING = a turn ran out of time after its tool rounds; FINAL CUT SHORT = the "
                                 "forced answer hit its token cap; 'STOP requested ... unload_all_models' = Bonsai was "
                                 "evicted for the card (a render/build); 'failure N/2' right after one = a reply died "
                                 "under that eviction."}
    if action == "watchdog":
        import stack_watch
        return stack_watch.status()
    if action == "card":
        out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                              os.path.join(_ROOT, "scripts", "vram_by_process.ps1")],
                             capture_output=True, text=True, timeout=60, creationflags=_NO_WINDOW)
        return {"vram_by_process": [ln for ln in (out.stdout or "").splitlines() if ln.strip()]}
    if action == "bonsai_timings":
        lines = [ln for ln in _tail(os.path.join(_DATA, "bonsai_server.log"), 3000)
                 if "prompt eval time" in ln or "       eval time" in ln]
        return {"last_timings": [ln.split("| ", 2)[-1] for ln in lines[-12:]],
                "read_this_way": "prompt eval = reading the prompt (tokens/s); eval = generating (tokens/s). Normal "
                                 "here: ~48 tok/s generation on a short context, ~30 on a long one; prompt eval "
                                 "400-600 tok/s. Far below = the card is spilling into shared RAM (see action card)."}
    if action == "hold_builds":
        until = video_queue.hold_builds(int(a.get("minutes") or 30), why="office_ops (Sophie)")
        _log(f"hold_builds until {datetime.datetime.fromtimestamp(until):%H:%M}")
        return {"held_until": datetime.datetime.fromtimestamp(until).isoformat(timespec="minutes")}
    if action == "release_builds":
        video_queue.release_builds()
        _log("release_builds")
        return {"released": True}
    if action in ("pause_job", "resume_job", "requeue_job"):
        res = video_queue.set_job_status(str(a.get("title") or ""),
                                         {"pause_job": "paused", "resume_job": "queued", "requeue_job": "queued"}[action])
        _log(f"{action} {a.get('title')!r} -> {res}")
        return res
    if action == "archive_draft":
        agent = str(a.get("agent") or "ilnora").strip()
        d = video_tool.load_draft(agent)
        if not d:
            return {"error": f"no saved draft for {agent}"}
        video_tool._archive_draft(agent, "archived")
        _log(f"archived {agent}'s draft '{d.get('title')}'")
        return {"archived": d.get("title"), "parts": len(d.get("parts") or [])}
    if action == "relaunch_watchdog":
        import stack_watch
        res = stack_watch.relaunch_watchdog()
        _log(f"relaunch_watchdog -> {res}")
        return {"result": res}
    return {"error": f"unknown action {action!r}"}


# ---------------------------------------------------------------- admin tasks
_FORBIDDEN = (r"\bformat-volume\b", r"\bdiskpart\b", r"\bclear-disk\b", r"\binitialize-disk\b", r"\bbcdedit\b",
              r"\bremove-item\b[^\n]*-recurse[^\n]*\\(windows|users)\\?", r"\bcipher\b[^\n]*/w", r"\bshutdown\b")


def propose_admin_task(title: str, script: str, explanation: str, risk_and_undo: str) -> dict:
    import engineer_tools
    title = " ".join(str(title or "").split())[:90]
    script = str(script or "").strip()
    if not title or len(script) < 10:
        return {"status": "refused", "why": "give a title and the PowerShell script"}
    if not str(explanation or "").strip() or not str(risk_and_undo or "").strip():
        return {"status": "refused", "why": "say WHAT it does and WHY, and WHAT COULD GO WRONG + how to undo it"}
    for bad in _FORBIDDEN:
        if re.search(bad, script, re.I):
            return {"status": "refused", "why": f"the script matches a forbidden pattern ({bad}) -- not even with his click"}
    os.makedirs(_ADMIN_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", title)[:40]
    path = os.path.join(_ADMIN_DIR, f"{stamp}_{safe}.ps1")
    log_path = os.path.join(_ADMIN_LOG_DIR, f"{stamp}_{safe}.log")
    header = (f"# ADMIN TASK (Sophie, {stamp}): {title}\n# Runs elevated ONLY on Barry's approve click.\n"
              f"$ErrorActionPreference = 'Continue'\nStart-Transcript -Path '{log_path}' -Force | Out-Null\n")
    footer = "\nStop-Transcript | Out-Null\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(header + script + footer)
    payload = json.dumps({"kind": "elevated", "script": path, "log": log_path})
    content = (f"ENGINEER TASK -- ADMIN (needs your click; Windows will show a yes/no box)\n\n{title}\n\n"
               f"WHAT + WHY: {explanation.strip()}\n\nWHAT COULD GO WRONG + UNDO: {risk_and_undo.strip()}\n\n"
               f"Script: {os.path.relpath(path, _ROOT)}\n\n{engineer_tools._MARKER}\n{payload}")
    aid = memory.queue_for_approval("engineer", "engineer_task", content)
    try:
        engineer_tools._refresh_journal()
    except Exception:  # noqa: BLE001
        pass
    _log(f"admin task proposed #{aid}: {title} -> {path}")
    return {"status": "queued", "approval_id": aid, "script": os.path.relpath(path, _ROOT),
            "note": "On his board. Nothing has run. When he approves, it runs elevated and the transcript lands in "
                    f"{os.path.relpath(log_path, _ROOT)} -- read it with read_project_file and tell him what happened."}


def run_elevated(script_path: str, log_path: str) -> dict:
    """Called from engineer_tools.run_approved for kind 'elevated' -- i.e. only after Barry's approve click."""
    if not script_path or not os.path.isfile(script_path) or not os.path.abspath(script_path).startswith(_ADMIN_DIR):
        return {"status": "failed", "why": "no such admin script (it must live in scripts/admin/)"}
    os.makedirs(_ADMIN_LOG_DIR, exist_ok=True)
    cmd = (f"$p = Start-Process -FilePath 'powershell.exe' -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass',"
           f"'-WindowStyle','Hidden','-File','{script_path}' -Verb RunAs -Wait -PassThru; exit $p.ExitCode")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=1800,
                           creationflags=_NO_WINDOW)
    except subprocess.TimeoutExpired:
        return {"status": "failed", "why": "the elevated run did not finish in 30 minutes"}
    if r.returncode == 1223 or "canceled by the user" in (r.stderr or "").lower():
        _log(f"admin task declined at the prompt: {script_path}")
        return {"status": "declined", "why": "the Windows prompt was declined -- nothing ran"}
    _log(f"admin task ran: {script_path} exit {r.returncode}")
    return {"status": "ok" if r.returncode == 0 else "failed", "exit": r.returncode, "log": log_path,
            "log_tail": _tail(log_path, 60)}
