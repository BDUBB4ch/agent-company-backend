"""
Real, restricted filesystem read access -- for Sophie (Engineer) only. Lets
her read actual project files instead of reasoning from abstract knowledge
alone, which is the whole point of her being an engineer who can fix THIS
system, not just discuss engineering theory in general.

Restricted to exactly two real directories: the Godot office and this
Python backend's own project -- the two things she'd realistically be asked
to help fix. Read-only: there is no write/delete capability here at all,
matching the same "draft/advise, never act unsupervised" boundary every
agent in this office has for anything real-world-facing (see agents.py's
_NEVER_PUBLISHES) -- reading a file to answer a question is research, the
same way web search already is for every agent, not an action.
"""
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT = os.path.normpath(os.path.join(_HERE, ".."))
ALLOWED_ROOTS = [
    os.path.normpath(r"C:\Users\Owner\Desktop\GODOT"),
    _PROJECT,                                                        # AgentCompanyBackend
    # 2026-09-06 (Barry: "fully capable"): she could not read the dashboard
    # she was asked to fix, nor the ComfyUI rig whose patches she must
    # re-apply after an update. Both are hers now, plus MyStudio.
    os.path.normpath(os.path.join(_PROJECT, "..", "AgentDashboard")),
]
try:
    from config import COMFY_DIR as _COMFY_DIR
    if _COMFY_DIR and os.path.isdir(_COMFY_DIR):
        ALLOWED_ROOTS.append(os.path.normpath(_COMFY_DIR))
except Exception:  # noqa: BLE001
    pass

# Godot's own error/warning log (already on by default for this project --
# same file the office's own Errors tab reads) lives under the OS user-data
# path, not inside the GODOT project folder, so it needs its own explicit
# allowance on top of ALLOWED_ROOTS above rather than moving the log or
# building a separate mechanism -- Sophie just gets to read it in place via
# the same read_project_file tool she already has. Project name matches
# project.godot's config/name ("Agent Company Office").
ALLOWED_EXTRA_FILES = [
    os.path.normpath(
        r"C:\Users\Owner\AppData\Roaming\Godot\app_userdata\Agent Company Office\logs\godot.log"
    ),
    os.path.normpath(os.path.join(_PROJECT, "..", "MyStudio.html")),
    os.path.normpath(os.path.join(_PROJECT, "..", "Start My Studio.bat")),
]

# 12,000 (was 50,000, cut 2026-08-16): at 50K chars (~12.5K tokens) PER
# READ, five read_project_file calls in one investigate loop totalled
# 71,643 tokens and blew straight past Bonsai's 65,536 window -- llama-server
# 400s honestly where Ollama silently truncates, which is how the old cap
# hid this for weeks. 12K keeps a five-read loop near ~15K tokens total.
MAX_FILE_CHARS = 12_000
MAX_LIST_ENTRIES = 300

# backend.log (see applog.py) accumulates across every restart in a session
# without ever clearing, marked off by "--- backend started ..." lines.
# Confirmed via a real live test that reading the whole thing makes Sophie
# report long-since-fixed errors from early restarts as if they were
# current problems -- a prompt instruction alone ("weigh the end more
# heavily") did not reliably fix this with her coding-focused model. The
# actual fix: only ever hand her the CURRENT session (since the last start
# marker), so stale history is structurally excluded rather than relying on
# the model to correctly judge recency from a raw mixed-history dump.
BACKEND_LOG_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "backend.log")
)
_SESSION_MARKER_RE = re.compile(r"\n--- backend started ")


# SECRETS ARE NEVER READ (2026-09-28, Barry: "yes do all 3"). The whole project
# folder was readable, .env included -- one read_project_file call would have
# put the Omnisend, WooCommerce and Microsoft Ads keys into her prompt and the
# 800-char trace log. One definition, used by every read path she has
# (read_file here, engineer_tools.search_project, engineer_tools.run_command).
_SECRET_NAME_RE = re.compile(
    r"^(?:\.env(?:\..+)?"                                   # .env, .env.local ...
    r"|.+\.(?:pem|key|pfx|p12|kdbx)"                          # key material
    r"|id_(?:rsa|ed25519|ecdsa|dsa)(?:\.pub)?"                # ssh keys
    r"|.*(?:secret|credential|token)s?(?:\.(?:json|txt|ya?ml|ini|cfg|env))?"  # secrets.json, token.txt
    r")$", re.I)
_SECRET_OK = {".env.example"}    # the template holds no values


def is_secret_path(path: str) -> bool:
    """True for a file that holds keys/tokens and must never be read by an agent."""
    name = os.path.basename(str(path or "")).strip().strip("\"'")
    if not name or name.lower() in _SECRET_OK:
        return False
    # Docs and code that merely MENTION secrets are fine to read.
    if os.path.splitext(name)[1].lower() in (".md", ".py", ".html", ".js", ".css", ".ps1", ".bat"):
        return False
    return bool(_SECRET_NAME_RE.match(name))


def _resolve_safe(path: str) -> str | None:
    """The real, normalized absolute path if it's genuinely inside one of
    the allowed roots (or one of the explicitly-allowed extra files), else
    None -- blocks path traversal (..\\..) and anything outside the allowed
    locations, including a path that merely starts with the same prefix
    string (e.g. a sibling folder named "GODOT-backup")."""
    candidate = os.path.normpath(os.path.abspath(path))
    if candidate in ALLOWED_EXTRA_FILES:
        return candidate
    for root in ALLOWED_ROOTS:
        if candidate == root or candidate.startswith(root + os.sep):
            return candidate
    return None


def read_file(path: str, start_line: int = 1, max_lines: int = 0) -> dict:
    """Returns {"path", "content", "truncated"} or {"error"}.

    2026-09-06: `start_line` (1-based) lets her walk a big file in chunks --
    main.py is ~5,000 lines and the 12K cap showed only the top. The reply
    says the total line count and the next start_line to ask for."""
    safe_path = _resolve_safe(path)
    if safe_path is None:
        return {"error": f"'{path}' is outside the build (AgentCompanyBackend, AgentDashboard, the ComfyUI rig, MyStudio)."}
    if is_secret_path(safe_path):
        return {"error": f"'{os.path.basename(safe_path)}' holds keys or tokens and is never read by an agent "
                         f"(Barry's rule, 2026-09-28). To check a key is SET, use system_health; "
                         f"for its names, read .env.example."}
    if not os.path.isfile(safe_path):
        return {"error": f"'{path}' is not a file, or doesn't exist. Try list_project_directory on its parent folder first."}
    try:
        with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as e:
        return {"error": f"Could not read '{path}': {e}"}

    note = None
    if safe_path == BACKEND_LOG_PATH:
        # Keep only the CURRENT session (since the last restart marker) --
        # see the constant's comment above for why this matters.
        matches = list(_SESSION_MARKER_RE.finditer(content))
        if matches:
            trimmed = content[matches[-1].start() + 1:]  # +1 to drop the leading \n, keep the marker line itself
            if len(trimmed) < len(content):
                note = "Older restarts from earlier in this session were trimmed -- this is the CURRENT session only."
            content = trimmed

    lines = content.splitlines(keepends=True)
    total_lines = len(lines)
    try:
        start = int(start_line or 1)
    except (TypeError, ValueError):
        start = 1
    # A NEGATIVE start_line reads the END (2026-09-28): -50 = the last 50
    # lines. Logs are where the newest evidence is, and the top of
    # bonsai_events.log is a week old.
    if start < 0:
        start = max(1, total_lines + start + 1)
    start = max(1, start)
    chunk = "".join(lines[start - 1:]) if start > 1 else content
    if max_lines and int(max_lines) > 0:
        chunk = "".join(lines[start - 1:start - 1 + int(max_lines)])
    truncated = len(chunk) > MAX_FILE_CHARS
    shown = chunk[:MAX_FILE_CHARS]
    end_line = start - 1 + shown.count("\n") + (0 if shown.endswith("\n") else 1)
    if truncated or end_line < total_lines:
        # Tell the model what it's missing so it reasons about the gap
        # instead of assuming it saw the whole file.
        cut_note = (f"PARTIAL: showing lines {start}-{end_line} of {total_lines:,} "
                    f"({len(content):,} chars total). To read on, call again with "
                    f"start_line={end_line + 1}. Say so if the answer might live in "
                    f"the part you have not read.")
        note = f"{note} {cut_note}" if note else cut_note
    return {
        "path": safe_path,
        "content": shown,
        "start_line": start,
        "end_line": end_line,
        "total_lines": total_lines,
        "truncated": truncated or end_line < total_lines,
        **({"note": note} if note else {}),
    }


def list_directory(path: str) -> dict:
    """Returns {"path", "entries", "truncated"} or {"error"}."""
    safe_path = _resolve_safe(path)
    if safe_path is None:
        return {"error": f"'{path}' is outside the build (AgentCompanyBackend, AgentDashboard, the ComfyUI rig, MyStudio)."}
    if not os.path.isdir(safe_path):
        return {"error": f"'{path}' is not a directory, or doesn't exist."}
    try:
        entries = sorted(os.listdir(safe_path))
    except OSError as e:
        return {"error": f"Could not list '{path}': {e}"}
    return {
        "path": safe_path,
        "entries": entries[:MAX_LIST_ENTRIES],
        "truncated": len(entries) > MAX_LIST_ENTRIES,
    }
