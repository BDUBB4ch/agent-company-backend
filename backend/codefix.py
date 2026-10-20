"""Propose-a-fix path for Sophie (Phase B of the coder upgrade, Barry's "go"
2026-08-28: "i want her to be able to make fixes if needed... she cant use
without my ok").

The shape mirrors Claude's own Edit tool, because it's the safest known way
to let a model change a file:
- the fix is an EXACT snippet replacement that must match EXACTLY ONCE
  (ambiguity refuses instead of guessing);
- nothing applies at proposal time -- the fix lands in the approval queue
  with an ELI17 explanation, and only Barry's approve click applies it;
- apply re-validates against the CURRENT file (it may have changed since the
  proposal), backs the file up first, writes temp-then-rename, syntax-checks
  the result, and RESTORES THE BACKUP on any check failure;
- backend .py files get a scheduled self-restart after a successful apply
  (the watchdog revives the process with the new code -- the house restart
  pattern); dashboard files need no restart, just a hard refresh.

Deliberate limits: text files only, inside the two project roots only, one
snippet per proposal. Bigger changes = more proposals, which keeps each
approval small enough for Barry to actually understand (his ELI17 rule).

2026-09-02 -- SHE CAN ACTUALLY FIX SHIT NOW (Barry: "I want her to actually
be able to fix shit"), inside the rule he set on 2026-08-31: "she never acts
without me unless its vital to the build, then she can go ahead and fix."
- `propose(..., vital=True)` applies IMMEDIATELY -- but only if the office
  shows a CODE-VERIFIED breakage right now (watch.vital_conditions: a
  must-be-up service down, a code-detected trace failure, an uncaught deck
  error, all within the last few hours). Her belief that it is vital is
  never enough; the gate is the same ground-truth idea as submit_agent_fix's.
  No live breakage = the proposal queues normally and waits for him.
- Every apply -- his click or hers -- now records its backup on the approval
  row, so ANY fix can be undone: `undo_fix(approval_id)` restores the file
  from that backup (backing up the current state first), same checks, same
  restart rule. POST /api/approvals/{id}/undo-fix.
- Backend .py applies now run scripts/preflight_check.py before the restart
  and RESTORE if it fails. A syntax check cannot see an undefined name; the
  2026-08-31 outage was exactly that, and an unattended fix must not be able
  to repeat it.
- Unattended applies are capped per day (setting auto_fix_max_per_day,
  default 3), can be switched off (auto_fix_enabled), and never touch the
  files that ARE the safety net (_UNATTENDED_DENY).
"""
import datetime
import difflib
import json
import os
import subprocess
import sys
import threading
import time

import memory

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ALLOWED_ROOTS = [
    _ROOT,                                                     # AgentCompanyBackend
    os.path.abspath(os.path.join(_ROOT, "..", "AgentDashboard")),
]
# 2026-09-06 (Barry: "fully capable"): the ComfyUI rig on D: too -- the two
# local patches an update wipes (gradient clip, GGUF gemma4) are hers to
# re-apply now -- plus MyStudio on the Desktop.
try:
    from config import COMFY_DIR as _COMFY_DIR
    if _COMFY_DIR and os.path.isdir(_COMFY_DIR):
        _ALLOWED_ROOTS.append(os.path.abspath(_COMFY_DIR))
except Exception:  # noqa: BLE001
    pass
_ALLOWED_FILES = {
    os.path.abspath(os.path.join(_ROOT, "..", "MyStudio.html")),
    os.path.abspath(os.path.join(_ROOT, "..", "Start My Studio.bat")),
}
_TEXT_EXTS = {".py", ".js", ".html", ".css", ".md", ".json", ".txt", ".bat", ".ps1", ".yaml", ".yml", ".toml", ".ini", ".cfg"}
_NEW_FILE_TAG = "<<<NEW FILE -- did not exist before this fix>>>"
_BACKUP_DIR = os.path.join(_ROOT, "data", "codefix_backups")
_MARKER = "===CODEFIX-PAYLOAD==="
_PREFLIGHT = os.path.join(_ROOT, "scripts", "preflight_check.py")

# Files an UNATTENDED fix may never touch: the fix machinery itself, the DB
# layer, the send path, and config. A bug in these is Barry-and-Claude work.
_UNATTENDED_DENY = {"codefix.py", "watch.py", "memory.py", "dispatch.py",
                    "omnisend_client.py", "config.py", "preflight_check.py",
                    "stack_watchdog.ps1"}


def _resolve(file_path: str, must_exist: bool = True):
    """Return absolute path if inside an allowed root with a text extension."""
    p = os.path.abspath(file_path if os.path.isabs(file_path)
                        else os.path.join(_ROOT, file_path))
    if os.path.splitext(p)[1].lower() not in _TEXT_EXTS:
        return None, "Only text source files can be changed this way (.py .js .html .css .md .json .txt .bat .ps1 .yaml .toml .ini)."
    if p not in _ALLOWED_FILES and not any(p == r or p.startswith(r + os.sep) for r in _ALLOWED_ROOTS):
        return None, "That path is outside the build (backend, dashboard, ComfyUI rig, MyStudio) -- refused."
    if "venv" + os.sep in p or os.sep + ".git" + os.sep in p:
        return None, "venv and .git contents are never edited this way."
    if must_exist and not os.path.isfile(p):
        return None, f"No such file: {p}"
    return p, None


def _setting_int(key: str, default: int) -> int:
    try:
        return int(memory.get_setting(key, str(default)))
    except (TypeError, ValueError):
        return default


def auto_fix_enabled() -> bool:
    return (memory.get_setting("auto_fix_enabled", "true") or "true").strip().lower() in ("1", "true", "yes", "on")


def _auto_fixes_today() -> int:
    since = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=24)).isoformat()
    with memory.get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM approvals WHERE action_type='code_fix' "
            "AND dispatch_status='auto_applied' AND decided_at > ?", (since,)).fetchone()
        return int(row["n"] if row else 0)


def _changed_lines(old: str, new: str) -> int:
    return sum(1 for d in difflib.ndiff(old.splitlines(), new.splitlines())
               if d[:1] in ("+", "-"))


def is_simple(old: str, new: str) -> bool:
    """SIMPLE, mechanically (Barry, 2026-09-02: "if its simple she should
    just fix it and tell me what she did"): a small snippet on both sides and
    only a few lines actually changed. Not a judgment of hers -- a size."""
    max_lines = _setting_int("auto_fix_simple_max_lines", 12)
    max_changed = _setting_int("auto_fix_simple_max_changed", 8)
    return (len(old.splitlines()) <= max_lines and len(new.splitlines()) <= max_lines
            and _changed_lines(old, new) <= max_changed)


def propose(file_path: str, explanation: str, old_snippet: str,
            new_snippet: str, risk_and_undo: str,
            apply_now: bool = False, reason: str = "",
            vital: bool = False, why_vital: str = "") -> dict:
    """Validate and queue a fix. Applies NOTHING -- unless `apply_now` is
    asked for AND the gate passes: the change is SIMPLE (small, measured) or
    the office verifiably shows a live breakage (vital). Either way it is
    recorded on the approval row with its backup, and undoable."""
    if vital and not apply_now:          # older calling shape
        apply_now, reason = True, why_vital or reason
    p, err = _resolve(file_path)
    if err:
        return {"status": "refused", "why": err}
    if not old_snippet or old_snippet == new_snippet:
        return {"status": "refused", "why": "old_snippet is empty or identical to new_snippet."}
    text = open(p, encoding="utf-8", errors="replace").read()
    count = text.count(old_snippet)
    if count != 1:
        return {"status": "refused",
                "why": (f"old_snippet appears {count} times in the file -- it must "
                        "match EXACTLY ONCE. Copy a longer, unique stretch of the "
                        "real file (read it first) and try again.")}

    diff = "\n".join(difflib.unified_diff(
        old_snippet.splitlines(), new_snippet.splitlines(),
        fromfile="before", tofile="after", lineterm=""))
    payload = json.dumps({"file": p, "old": old_snippet, "new": new_snippet})
    content = (
        f"CODE FIX PROPOSAL -- {os.path.relpath(p, os.path.dirname(_ROOT))}\n\n"
        f"{explanation.strip()}\n\n"
        f"RISK AND UNDO: {risk_and_undo.strip()}\n\n"
        + (f"APPLY NOW (her reason): {reason.strip()}\n\n" if apply_now else "")
        + f"THE CHANGE:\n{diff}\n\n"
        f"{_MARKER}\n{payload}"
    )
    approval_id = memory.queue_for_approval("engineer", "code_fix", content, file_path=p)

    if not apply_now:
        refresh_journal()          # a pending fix is something she should know she proposed
        return {"status": "queued",
                "approval_id": approval_id,
                "note": ("Queued for Barry's approval -- NOTHING has been changed. "
                         "Tell him it's waiting in Pending Review and summarize the "
                         "explanation; never claim it's applied.")}

    # --- THE GATE: simple OR vital, never just "she said so" ---------------
    gate = _apply_gate(p, old_snippet, new_snippet)
    if gate:
        return {"status": "queued",
                "approval_id": approval_id,
                "apply_refused": gate,
                "note": ("You asked to apply this yourself, but the gate did not pass: "
                         + gate + " So it is QUEUED for Barry's approval like any "
                         "other fix -- nothing has changed. Tell him plainly why you "
                         "wanted to act and that it is waiting on him.")}
    result = _apply(approval_id, auto=True, why=reason)
    if result.get("status") != "applied":
        return {"status": result.get("status"), "approval_id": approval_id,
                "why": result.get("why"),
                "note": ("The apply FAILED and the file was left as it was (see why). "
                         "The proposal is still in Barry's queue. Tell him exactly this.")}
    return {"status": "auto_applied", "approval_id": approval_id,
            "backup": result.get("backup"), "restarting": result.get("restarting"),
            "note": ("APPLIED BY YOU. Tell Barry plainly, in this reply: what was "
                     "wrong, exactly what you changed (file + one line on the "
                     "edit), and that he can undo it by telling you 'undo fix "
                     f"#{approval_id}'. " + result.get("note", ""))}


def propose_write(file_path: str, content: str, explanation: str, risk_and_undo: str,
                  apply_now: bool = False, reason: str = "") -> dict:
    """WHOLE-FILE write: create a NEW file, or replace an existing one
    entirely (2026-09-06, Barry: "build anything i need" -- a snippet
    replace cannot create a module). Same queue, same backup, same undo,
    same preflight as a snippet fix.

    Unattended rule: a NEW file that nothing imports cannot break the build,
    so a new file passes the gate on its own (preflight still runs for
    backend .py). Overwriting an existing file passes only if the diff is
    SIMPLE or the build is verifiably broken -- her say-so never enough."""
    p, err = _resolve(file_path, must_exist=False)
    if err:
        return {"status": "refused", "why": err}
    if not isinstance(content, str) or not content.strip():
        return {"status": "refused", "why": "content is empty."}
    if len(content) > 200_000:
        return {"status": "refused", "why": "content over 200K chars -- split the file."}
    existed = os.path.isfile(p)
    old_text = open(p, encoding="utf-8", errors="replace").read() if existed else ""
    if existed and old_text == content:
        return {"status": "refused", "why": "the file already has exactly this content."}
    if not os.path.isdir(os.path.dirname(p)):
        return {"status": "refused", "why": f"the folder does not exist: {os.path.dirname(p)} -- create files in an existing folder."}
    if p.endswith(".py"):
        try:
            compile(content, p, "exec")
        except SyntaxError as e:
            return {"status": "refused", "why": f"that Python does not even parse: {e}. Fix it and try again."}

    diff = "\n".join(difflib.unified_diff(
        old_text.splitlines(), content.splitlines(),
        fromfile="before" if existed else "(new file)", tofile="after", lineterm="", n=2))
    if len(diff) > 6000:
        diff = diff[:6000] + "\n... (diff trimmed; full content in the payload)"
    payload = json.dumps({"file": p, "mode": "write", "new": content, "existed": existed})
    content_row = (
        f"CODE FIX PROPOSAL -- {'NEW FILE' if not existed else 'REWRITE'} "
        f"{os.path.relpath(p, os.path.dirname(_ROOT)) if p.startswith(os.path.dirname(_ROOT)) else p}\n\n"
        f"{explanation.strip()}\n\n"
        f"RISK AND UNDO: {risk_and_undo.strip()}\n\n"
        + (f"APPLY NOW (her reason): {reason.strip()}\n\n" if apply_now else "")
        + f"THE CHANGE ({len(content.splitlines())} lines):\n{diff}\n\n"
        f"{_MARKER}\n{payload}"
    )
    approval_id = memory.queue_for_approval("engineer", "code_fix", content_row, file_path=p)
    if not apply_now:
        refresh_journal()
        return {"status": "queued", "approval_id": approval_id,
                "note": ("Queued for Barry's approval -- NOTHING has been written. Tell him "
                         "it's waiting in Pending Review; never claim the file exists yet.")}
    gate = _write_gate(p, existed, old_text, content)
    if gate:
        return {"status": "queued", "approval_id": approval_id, "apply_refused": gate,
                "note": ("You asked to apply this yourself, but the gate did not pass: " + gate
                         + " It is QUEUED for Barry -- nothing has been written. Say so plainly.")}
    result = _apply(approval_id, auto=True, why=reason)
    if result.get("status") != "applied":
        return {"status": result.get("status"), "approval_id": approval_id, "why": result.get("why"),
                "note": "The write FAILED and nothing was left changed. The proposal is still in Barry's queue."}
    return {"status": "auto_applied", "approval_id": approval_id, "backup": result.get("backup"),
            "restarting": result.get("restarting"),
            "note": ("WRITTEN BY YOU. Tell Barry plainly: which file, what it does, and that he can "
                     f"undo it with 'undo fix #{approval_id}'. " + result.get("note", ""))}


def _write_gate(path: str, existed: bool, old: str, new: str) -> str | None:
    if not auto_fix_enabled():
        return "unattended fixes are switched off (auto_fix_enabled)."
    if os.path.basename(path) in _UNATTENDED_DENY:
        return f"{os.path.basename(path)} is on the never-unattended list."
    cap = _setting_int("auto_fix_max_per_day", 6)
    if _auto_fixes_today() >= cap:
        return f"you have already applied {cap} fixes yourself in the last 24h (the daily cap)."
    if not existed:
        return None                      # a new file nothing imports is harmless; preflight still runs
    if is_simple(old, new):
        return None
    try:
        import watch
        if watch.vital_conditions():
            return None
    except Exception as e:  # noqa: BLE001
        return f"could not verify the office's state ({e})."
    return ("rewriting an existing file is not SIMPLE (%d lines changed) and the office shows no "
            "code-verified breakage, so it waits for Barry." % _changed_lines(old, new))


def _apply_gate(path: str, old: str, new: str) -> str | None:
    """Return a reason string if an unattended apply is NOT allowed.
    Passes when the change is SIMPLE (measured size) or the office shows a
    code-verified live breakage (vital). Her say-so alone never passes."""
    if not auto_fix_enabled():
        return "unattended fixes are switched off (auto_fix_enabled)."
    if os.path.basename(path) in _UNATTENDED_DENY:
        return f"{os.path.basename(path)} is on the never-unattended list."
    cap = _setting_int("auto_fix_max_per_day", 6)
    if _auto_fixes_today() >= cap:
        return f"you have already applied {cap} fixes yourself in the last 24h (the daily cap)."
    if is_simple(old, new):
        return None
    try:
        import watch
        conditions = watch.vital_conditions()
    except Exception as e:  # noqa: BLE001
        return f"could not verify the office's state ({e})."
    if conditions:
        return None
    return ("the change is not SIMPLE (%d lines changed; the simple limit is %d, "
            "snippets up to %d lines) and the office shows NO code-verified "
            "breakage right now, so this one waits for Barry. A bigger fix can be "
            "several small ones." % (_changed_lines(old, new),
                                     _setting_int("auto_fix_simple_max_changed", 8),
                                     _setting_int("auto_fix_simple_max_lines", 12)))


def last_applied_fix_id() -> int | None:
    with memory.get_db() as conn:
        row = conn.execute(
            "SELECT id FROM approvals WHERE action_type='code_fix' AND "
            "dispatch_status IN ('applied','auto_applied') ORDER BY id DESC LIMIT 1").fetchone()
        return int(row["id"]) if row else None


def _syntax_ok(path: str) -> str | None:
    """Return an error string if the changed file fails a syntax check."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".py":
        try:
            compile(open(path, encoding="utf-8").read(), path, "exec")
        except SyntaxError as e:
            return f"Python syntax error after apply: {e}"
    elif ext == ".json":
        try:
            json.load(open(path, encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            return f"JSON invalid after apply: {e}"
    # .js/.html/.css: no reliable in-process checker; the backup covers it.
    return None


def _is_backend_py(path: str) -> bool:
    return path.startswith(os.path.join(_ROOT, "backend") + os.sep) and path.endswith(".py")


def _preflight_ok(path: str) -> str | None:
    """scripts/preflight_check.py after a backend edit: undefined names,
    cross-module refs, real imports, duplicate routes. A syntax check cannot
    see any of those (the 2026-08-31 eleven-hour outage)."""
    if not _is_backend_py(path) or not os.path.isfile(_PREFLIGHT):
        return None
    try:
        r = subprocess.run([sys.executable, _PREFLIGHT], capture_output=True,
                           text=True, timeout=90, cwd=_ROOT)
    except Exception as e:  # noqa: BLE001
        return f"preflight could not run: {e}"
    if r.returncode != 0:
        tail = (r.stdout or "")[-1200:] + (r.stderr or "")[-400:]
        return "preflight FAILED after apply:\n" + tail
    return None


def _schedule_self_restart():
    # The house restart pattern: kill the process, the watchdog revives it
    # with the new code within ~45s. Delayed so the approve response flushes.
    def _die():
        time.sleep(3)
        os._exit(0)
    threading.Thread(target=_die, daemon=True).start()


def _write_checked(p: str, new_text: str, old_text: str, stamp: str) -> dict:
    """Back up, write temp+rename, syntax + preflight; restore on failure.

    2026-09-06: the backup name carries a counter as well as the second-
    resolution stamp -- two applies to the same file inside one second
    (measured in the battery) used to share a filename, so the second
    overwrote the first fix's backup and its undo silently did nothing."""
    os.makedirs(_BACKUP_DIR, exist_ok=True)
    backup = os.path.join(_BACKUP_DIR, f"{stamp}_{os.path.basename(p)}")
    n = 1
    while os.path.exists(backup):
        n += 1
        backup = os.path.join(_BACKUP_DIR, f"{stamp}_{n}_{os.path.basename(p)}")
    open(backup, "w", encoding="utf-8").write(old_text)

    tmp = p + ".codefix.tmp"
    open(tmp, "w", encoding="utf-8").write(new_text)
    os.replace(tmp, p)

    err = _syntax_ok(p) or _preflight_ok(p)
    if err:
        _restore(p, old_text)
        return {"status": "failed_and_restored", "why": err, "backup": backup,
                "note": "The file was restored -- nothing is broken."}
    return {"status": "applied", "backup": backup}


def _restore(p: str, old_text: str) -> None:
    """Put a file back -- and if it did not exist before, remove it."""
    if old_text == _NEW_FILE_TAG:
        try:
            os.remove(p)
        except OSError:
            pass
    else:
        open(p, "w", encoding="utf-8").write(old_text)


def _record(approval_id: int, dispatch_status: str, detail: dict) -> None:
    with memory.get_db() as conn:
        conn.execute(
            "UPDATE approvals SET dispatch_status = ?, dispatch_response = ? WHERE id = ?",
            (dispatch_status, json.dumps(detail)[:2000], approval_id))


def _apply(approval_id: int, auto: bool = False, why: str = "") -> dict:
    entry = memory.get_output_by_id(approval_id)
    if not entry or entry.get("action_type") != "code_fix":
        return {"status": "failed", "why": "not a code_fix approval"}
    content = entry.get("content", "")
    if _MARKER not in content:
        return {"status": "failed", "why": "proposal payload missing"}
    try:
        payload = json.loads(content.split(_MARKER, 1)[1].strip())
    except Exception as e:  # noqa: BLE001
        return {"status": "failed", "why": f"payload unreadable: {e}"}

    write_mode = payload.get("mode") == "write"
    p, err = _resolve(payload.get("file", ""), must_exist=not write_mode)
    if err:
        return {"status": "failed", "why": err}
    stamp = time.strftime("%Y%m%d-%H%M%S")
    if write_mode:
        new = payload.get("new", "")
        existed_now = os.path.isfile(p)
        text = open(p, encoding="utf-8", errors="replace").read() if existed_now else _NEW_FILE_TAG
        if not payload.get("existed") and existed_now:
            return {"status": "failed",
                    "why": "That file has been created since this was proposed -- re-propose against it."}
        result = _write_checked(p, new, text, stamp)
    else:
        old, new = payload.get("old", ""), payload.get("new", "")
        text = open(p, encoding="utf-8", errors="replace").read()
        if text.count(old) != 1:
            return {"status": "failed",
                    "why": ("The file changed since this fix was proposed -- the "
                            "snippet no longer matches exactly once. Ask Sophie to "
                            "re-propose against the current file.")}
        result = _write_checked(p, text.replace(old, new, 1), text, stamp)
    if result["status"] != "applied":
        _record(approval_id, "apply_failed", result)
        return result

    needs_restart = _is_backend_py(p)
    detail = {"backup": result["backup"], "file": p, "auto": auto,
              "why_vital": why, "applied_at": datetime.datetime.now(datetime.UTC).isoformat()}
    if auto:
        memory.decide_approval(approval_id, True)      # so it shows in the Out box, not Pending
    _record(approval_id, "auto_applied" if auto else "applied", detail)
    refresh_journal()
    if needs_restart:
        _schedule_self_restart()
    return {"status": "applied",
            "backup": result["backup"],
            "restarting": needs_restart,
            "note": ("Applied. " + ("Backend is restarting itself -- the watchdog "
                     "brings it back within ~45 seconds." if needs_restart else
                     "No restart needed -- hard-refresh the dashboard if this "
                     "was a UI file."))}


def apply_fix(approval_id: int) -> dict:
    """Apply an approved code_fix. Called ONLY from the approve endpoint."""
    return _apply(approval_id, auto=False)


def undo_fix(approval_id: int) -> dict:
    """Put the file back the way it was before this fix (his click OR hers).
    The current state is backed up first, so an undo can itself be undone
    by hand. Same checks and the same restart rule as an apply."""
    entry = memory.get_output_by_id(approval_id)
    if not entry or entry.get("action_type") != "code_fix":
        return {"status": "failed", "why": "not a code_fix approval"}
    try:
        detail = json.loads(entry.get("dispatch_response") or "{}")
    except ValueError:
        detail = {}
    if entry.get("dispatch_status") not in ("applied", "auto_applied"):
        return {"status": "failed", "why": f"this fix is not applied (status: {entry.get('dispatch_status') or 'never applied'})"}
    backup = detail.get("backup")
    if not backup or not os.path.isfile(backup):
        return {"status": "failed", "why": "no backup recorded for this fix -- restore by hand from data/codefix_backups/"}
    p, err = _resolve(detail.get("file", ""), must_exist=False)
    if err:
        return {"status": "failed", "why": err}
    current = open(p, encoding="utf-8", errors="replace").read() if os.path.isfile(p) else _NEW_FILE_TAG
    original = open(backup, encoding="utf-8", errors="replace").read()
    if current == original:
        _record(approval_id, "undone", {**detail, "undone_at": datetime.datetime.now(datetime.UTC).isoformat()})
        return {"status": "undone", "note": "File already matched the backup -- nothing to change."}
    stamp = time.strftime("%Y%m%d-%H%M%S") + "_before-undo"
    if original == _NEW_FILE_TAG:
        # The fix CREATED this file: undo = remove it (current content backed up first).
        os.makedirs(_BACKUP_DIR, exist_ok=True)
        pre = os.path.join(_BACKUP_DIR, f"{stamp}_{os.path.basename(p)}")
        open(pre, "w", encoding="utf-8").write(current)
        try:
            os.remove(p)
        except OSError as e:
            return {"status": "failed", "why": f"could not remove the created file: {e}"}
        result = {"status": "applied", "backup": pre}
        if _is_backend_py(p):
            pf = _preflight_ok(p)
            if pf:
                open(p, "w", encoding="utf-8").write(current)
                return {"status": "failed_and_restored", "why": pf,
                        "note": "Removing the file broke the build (something imports it) -- put back."}
    else:
        result = _write_checked(p, original, current, stamp)
    if result["status"] != "applied":
        return result
    _record(approval_id, "undone", {**detail, "undone_at": datetime.datetime.now(datetime.UTC).isoformat(),
                                    "pre_undo_backup": result["backup"]})
    refresh_journal()
    needs_restart = _is_backend_py(p)
    if needs_restart:
        _schedule_self_restart()
    # Hand her the real before/after so she reports the undo from data. In
    # the first live undo she described the direction backwards from memory.
    restored_diff = "\n".join(difflib.unified_diff(
        current.splitlines(), ("" if original == _NEW_FILE_TAG else original).splitlines(),
        fromfile="before undo (the fixed version)", tofile="after undo (restored original)",
        lineterm="", n=1))[:1500]
    return {"status": "undone", "restarting": needs_restart, "file": p,
            "what_changed": restored_diff,
            "note": ("Restored from the backup. Describe it to Barry FROM what_changed above "
                     "(lines with - were the fix, lines with + are what is back now)."
                     + (" Backend restarting itself." if needs_restart
                        else " Hard-refresh the dashboard if it was a UI file."))}


_JOURNAL_SOURCE = "my-code-fixes.md"


def _fix_summary_line(row: dict) -> str:
    """One line per fix: what it was, where it stands, how to undo."""
    content = row.get("content") or ""
    head = content.split(_MARKER)[0].split("===ENGINEER-TASK===")[0].splitlines()
    title = head[0].replace("CODE FIX PROPOSAL -- ", "").strip() if head else "?"
    what = next((ln.strip() for ln in head[1:] if ln.strip()), "")[:220]
    ds = row.get("dispatch_status") or ""
    st = row.get("status") or ""
    is_task = row.get("action_type") == "engineer_task"
    if is_task:
        state = ("WAITING ON BARRY" if st == "pending" else "REJECTED by Barry" if st == "rejected"
                 else f"RAN ({ds or 'done'})")
        cmd = next((ln.strip() for ln in head if ln.startswith("COMMAND:")), title)
        out = ""
        try:
            resp = json.loads(row.get("dispatch_response") or "{}")
            out = (resp.get("output") or resp.get("why") or "")[:300].replace("\n", " / ")
        except ValueError:
            pass
        when = (row.get("decided_at") or row.get("created_at") or "")[:16].replace("T", " ")
        return f"- task #{row['id']} [{state}] {when} -- {cmd}" + (f" => {out}" if out else "")
    state = {"auto_applied": "APPLIED BY ME", "applied": "APPLIED (Barry approved)",
             "undone": "UNDONE", "apply_failed": "APPLY FAILED, file untouched"}.get(
        ds, "WAITING ON BARRY" if st == "pending" else ("REJECTED by Barry" if st == "rejected" else st))
    when = (row.get("decided_at") or row.get("created_at") or "")[:16].replace("T", " ")
    undo = " -- undo: say 'undo fix #%d'" % row["id"] if ds in ("applied", "auto_applied") else ""
    return f"- fix #{row['id']} [{state}] {when} -- {title}: {what}{undo}"


def refresh_journal() -> None:
    """SHE KNOWS WHAT SHE DID (Barry, 2026-09-02: "she needs to know what she
    did and how to undo it"). Rebuilds one on-demand, routed fact in her own
    brain from the approvals table -- the DB is the truth, this is her memory
    of it. Superseded, never deleted, on every apply/undo. Never raises."""
    try:
        rows = []
        with memory.get_db() as conn:
            for r in conn.execute(
                    "SELECT * FROM approvals WHERE action_type IN ('code_fix','engineer_task') ORDER BY id DESC LIMIT 40"):
                rows.append(dict(r))
        body = (
            "USE WHEN: asked what you changed, fixed, applied or undid; which fix is "
            "waiting on Barry; which fix to undo; your code-fix history.\n\n"
            "MY CODE FIXES -- newest first. The live truth is the list_code_fixes tool; "
            "this is my memory of it. Every applied fix has a backup and can be put back "
            "with undo_code_fix -- but ONLY when Barry asks me to undo it.\n\n"
            + ("\n".join(_fix_summary_line(r) for r in rows) if rows else "- none yet")
        )
        category = "private:Engineer"
        with memory.get_db() as conn:
            conn.execute("UPDATE facts SET status='superseded' WHERE category=? AND "
                         "source_name=? AND status='active'", (category, _JOURNAL_SOURCE))
        memory.add_fact(category, body, source_name=_JOURNAL_SOURCE, title="My code fixes -- what I changed and how to undo it")
    except Exception as e:  # noqa: BLE001
        print(f"[codefix] journal refresh failed: {e}")


def list_fixes(limit: int = 50) -> list[dict]:
    """Every code fix, newest first: pending / applied / auto_applied / undone."""
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT id, action_type, status, dispatch_status, dispatch_response, created_at, decided_at, file_path, "
            "substr(content, 1, 600) AS head FROM approvals WHERE action_type IN ('code_fix','engineer_task') "
            "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        head = d.pop("head") or ""
        d["title"] = head.split("\n", 1)[0]
        if d.get("action_type") == "engineer_task":
            d["command"] = next((ln.strip() for ln in head.splitlines() if ln.startswith("COMMAND:")), "")
            try:
                resp = json.loads(d.get("dispatch_response") or "{}")
                d["output"] = (resp.get("output") or resp.get("why") or resp.get("note") or "")[:2000]
            except ValueError:
                d["output"] = ""
        d.pop("dispatch_response", None)
        out.append(d)
    return out
