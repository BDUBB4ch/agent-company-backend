"""Sophie notices when this MACHINE changes. Not an antivirus -- the other half.

Barry, 2026-09-19, after asking how possible it is to give her her own
antivirus: "do both."

WHAT THIS IS, AND WHY IT IS NOT AN AV. Real protection lives in a kernel-mode
filesystem filter driver, and Windows will not load one that is not signed
through Microsoft's attestation process; registering as the machine's
antivirus is gated behind the Microsoft Virus Initiative besides. Neither door
is open to us, and a hand-rolled scanner with no signature feed would be
strictly worse than Defender while feeling like more. So Defender keeps doing
the catching (pc_security.py watches and drives it) and this module does the
thing Defender does NOT do:

    Defender answers "is this file known to be bad?"
    This answers  "did something about my machine change?"

That second question is what actually gets asked when something gets in --
because the thing that got in is, by definition, not known-bad yet. Every
persistence technique worth the name has to write to a startup surface, and
almost everything hostile arrives as an unsigned binary somewhere it has no
business being.

FOUR CHECKS, all LOCAL. No signatures, no vendor, no cloud, no outbound
request of any kind -- it reads this machine and nothing else, so Offline Mode
changes nothing here.

  1. STARTUP SURFACES -- Run keys + Startup folders (Win32_StartupCommand),
     enabled scheduled tasks, and auto-start services. A new one appearing is
     a finding. This is where persistence has to land.
  2. NEW EXECUTABLES in the folders that matter (the office tree, Desktop,
     Downloads), with their Authenticode signature state. Unsigned and new, in
     a place code does not normally appear, is the loudest honest signal
     available without a driver.
  3. CODE INTEGRITY -- a sha256 of every backend/dashboard/script source file.
     Anything editing the office itself gets named. (This would have caught
     Claude deleting client-errors.js on 2026-09-17, which nothing did.)
  4. ADMIN ACCOUNTS -- a new local administrator is a takeover, full stop.

HOW IT BEHAVES. The first run takes a BASELINE and reports nothing -- there is
no way to know whether what is already here is legitimate, and pretending
otherwise would bury him in noise on day one. After that, only DIFFS are
findings. Anything he says is fine gets folded into the baseline and never
asked again (`accept`).

⚠️ IT IS A CHANGE DETECTOR, NOT A VERDICT. It says "this is new", never "this
is malware" -- it cannot know. Installing something legitimate will produce
findings, and that is correct behaviour, not a false positive.

Never raises: every probe is wrapped, and a failure is reported as text,
because this rides inside Sophie's 15-minute watch.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA = os.path.join(_REPO, "data")
_BASELINE = os.path.join(_DATA, "host_baseline.json")

# Where a new executable actually matters. His whole disk would be noise (and
# slow); these are the places code arrives and the place code runs from.
_WATCH_DIRS = [
    _REPO,
    os.path.join(os.path.expanduser("~"), "Desktop"),
    os.path.join(os.path.expanduser("~"), "Downloads"),
]
_EXE_EXT = (".exe", ".dll", ".bat", ".cmd", ".ps1", ".vbs", ".scr", ".msi", ".jar")
# Folders that are noisy by construction and owned by tools we installed on
# purpose. Skipped for the executable sweep only -- integrity still covers our
# own source.
_SKIP_DIRS = {"venv", "node_modules", ".git", "__pycache__", "tools", "models",
              "data", "output", "_done", ".cache", "site-packages"}
_MAX_EXE_FILES = 4000          # a ceiling so a stuffed Downloads cannot stall the watch

# Source files whose contents are hashed. Small, fast, and the thing an
# attacker (or a careless agent) would actually modify.
_CODE_DIRS = [
    (os.path.join(_REPO, "backend"), (".py",)),
    (os.path.join(_REPO, "scripts"), (".py",)),
    (os.path.join(os.path.dirname(_REPO), "AgentDashboard"), (".js", ".html", ".css")),
]


def _ps(script: str, timeout: int = 40) -> str:
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                             capture_output=True, text=True, timeout=timeout,
                             creationflags=_NO_WINDOW)
        return (out.stdout or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _json_ps(script: str, timeout: int = 40):
    raw = _ps(script, timeout)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:  # noqa: BLE001
        return []
    return data if isinstance(data, list) else [data]


# --- the four probes ---------------------------------------------------------
def startup_surfaces() -> dict:
    """{identity: description} for everything that runs itself at boot/login."""
    out: dict[str, str] = {}
    for row in _json_ps(
            "$ErrorActionPreference='SilentlyContinue';"
            "Get-CimInstance Win32_StartupCommand |"
            " Select-Object Name,Command,Location | ConvertTo-Json -Compress"):
        name = (row.get("Name") or "?").strip()
        loc = (row.get("Location") or "?").strip()
        out[f"startup::{loc}::{name}"] = (row.get("Command") or "")[:200]
    for row in _json_ps(
            "$ErrorActionPreference='SilentlyContinue';"
            "Get-ScheduledTask | Where-Object {$_.State -ne 'Disabled'} |"
            " Select-Object TaskName,TaskPath | ConvertTo-Json -Compress"):
        out[f"task::{(row.get('TaskPath') or '')}{row.get('TaskName')}"] = "scheduled task"
    for row in _json_ps(
            "$ErrorActionPreference='SilentlyContinue';"
            "Get-CimInstance Win32_Service | Where-Object {$_.StartMode -eq 'Auto'} |"
            " Select-Object Name,PathName | ConvertTo-Json -Compress"):
        out[f"service::{row.get('Name')}"] = (row.get("PathName") or "")[:200]
    return out


def local_admins() -> list[str]:
    rows = _json_ps("$ErrorActionPreference='SilentlyContinue';"
                    "Get-LocalGroupMember -Group Administrators |"
                    " Select-Object Name | ConvertTo-Json -Compress", timeout=25)
    return sorted({(r.get("Name") or "").strip() for r in rows if r.get("Name")})


def _walk_executables() -> dict:
    """{path: mtime_size} for executable-ish files in the watched folders."""
    found: dict[str, str] = {}
    seen = 0
    for root_dir in _WATCH_DIRS:
        if not os.path.isdir(root_dir):
            continue
        for root, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if d.lower() not in _SKIP_DIRS and not d.startswith(".")]
            for name in files:
                if not name.lower().endswith(_EXE_EXT):
                    continue
                path = os.path.join(root, name)
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                found[path] = f"{int(st.st_mtime)}:{st.st_size}"
                seen += 1
                if seen >= _MAX_EXE_FILES:
                    return found
    return found


# SignatureStatus, because ConvertTo-Json renders the enum as an INTEGER.
# ⚠️ Found in testing 2026-09-19: the first version compared that number
# against strings, so every check fell through to the "signed, probably an
# install you did" branch -- an UNSIGNED probe .bat was reported as signed. A
# security tool that gets this backwards is worse than not having it. The
# PowerShell now stringifies it and this map is the belt.
_SIG_STATUS = {0: "Valid", 1: "UnknownError", 2: "NotSigned", 3: "HashMismatch",
               4: "NotTrusted", 5: "NotSupportedFileFormat", 6: "Incompatible"}
_TRUSTED = ("Valid",)


def signature_of(path: str) -> tuple[str, bool]:
    """(human status, is_trusted). Anything that is not provably Valid is NOT
    trusted -- unknown counts as untrusted, never the other way round."""
    safe = path.replace("'", "''")
    rows = _json_ps("$ErrorActionPreference='SilentlyContinue';"
                    f"Get-AuthenticodeSignature -LiteralPath '{safe}' |"
                    " Select-Object @{n='Status';e={$_.Status.ToString()}},"
                    "@{n='Signer';e={$_.SignerCertificate.Subject}} |"
                    " ConvertTo-Json -Compress", timeout=25)
    if not rows:
        return "unknown", False
    raw = rows[0].get("Status")
    status = _SIG_STATUS.get(raw, str(raw)) if isinstance(raw, int) else str(raw or "unknown")
    signer = (rows[0].get("Signer") or "").split(",")[0].replace("CN=", "").strip()
    return status + (f" ({signer})" if signer else ""), status in _TRUSTED


def _code_hashes() -> dict:
    out: dict[str, str] = {}
    for folder, exts in _CODE_DIRS:
        if not os.path.isdir(folder):
            continue
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if d.lower() not in _SKIP_DIRS and not d.startswith(".")]
            for name in files:
                if not name.lower().endswith(exts):
                    continue
                path = os.path.join(root, name)
                try:
                    with open(path, "rb") as fh:
                        out[os.path.relpath(path, os.path.dirname(_REPO))] = \
                            hashlib.sha256(fh.read()).hexdigest()[:16]
                except OSError:
                    continue
    return out


# --- baseline ----------------------------------------------------------------
def _load() -> dict:
    try:
        with open(_BASELINE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return {}


def _save(data: dict) -> None:
    os.makedirs(_DATA, exist_ok=True)
    tmp = _BASELINE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)
    os.replace(tmp, _BASELINE)


def snapshot() -> dict:
    return {
        "taken": time.strftime("%Y-%m-%d %H:%M"),
        "startup": startup_surfaces(),
        "admins": local_admins(),
        "executables": _walk_executables(),
        "code": _code_hashes(),
    }


def accept(reason: str = "") -> dict:
    """Fold everything as it is RIGHT NOW into the baseline. What he blesses is
    never asked about again."""
    snap = snapshot()
    snap["accepted_reason"] = reason or "accepted by Barry"
    _save(snap)
    return {"ok": True, "baseline_taken": snap["taken"],
            "startup_entries": len(snap["startup"]),
            "executables": len(snap["executables"]),
            "code_files": len(snap["code"])}


# --- the check ---------------------------------------------------------------
def check(max_findings: int = 12) -> list[str]:
    """Diffs against the baseline. First ever run takes the baseline silently."""
    findings: list[str] = []
    try:
        base = _load()
        snap = snapshot()
        if not base:
            _save(snap)
            return [f"HOST BASELINE TAKEN -- {len(snap['startup'])} startup entries, "
                    f"{len(snap['executables'])} executables, {len(snap['code'])} source files "
                    f"recorded. From now on anything NEW here is a finding. Nothing is wrong; "
                    f"this is the first look."]

        # 1. startup surfaces
        new_startup = [k for k in snap["startup"] if k not in (base.get("startup") or {})]
        for key in new_startup[:4]:
            kind, _, rest = key.partition("::")
            findings.append(
                f"NEW STARTUP ENTRY -- {rest} ({kind}) now runs by itself at boot or login: "
                f"{snap['startup'][key][:140]}. If that was you installing something, say so "
                f"and it goes in the baseline. If it was not, it is how something stays.")
        if len(new_startup) > 4:
            findings.append(f"...and {len(new_startup) - 4} more new startup entries.")

        # 2. new administrators
        new_admins = [a for a in snap["admins"] if a not in (base.get("admins") or [])]
        for who in new_admins:
            findings.append(f"NEW LOCAL ADMINISTRATOR -- {who} was added to the Administrators "
                            f"group. If you did not do that, treat it as a takeover.")

        # 3. new executables, signature named
        old_exe = base.get("executables") or {}
        new_exe = [p for p in snap["executables"] if p not in old_exe]
        # newest first -- a thing that appeared 20 seconds ago matters more
        new_exe.sort(key=lambda p: snap["executables"][p], reverse=True)
        for path in new_exe[:3]:
            sig, trusted = signature_of(path)
            findings.append(
                f"NEW {'' if trusted else 'UNSIGNED '}EXECUTABLE -- {path}"
                f" [{sig}]." + (" Signed by a trusted publisher, so it is most likely an "
                                "install you did."
                                if trusted else
                                " Nothing vouches for this file. That is the shape of something "
                                "that arrived rather than something you installed -- though a "
                                "script you or I wrote looks identical, so it is a question, "
                                "not a verdict."))
        if len(new_exe) > 3:
            findings.append(f"...and {len(new_exe) - 3} more new executables in the watched folders.")

        # 4. office code changed
        old_code = base.get("code") or {}
        changed = [p for p, h in snap["code"].items() if old_code.get(p) and old_code[p] != h]
        gone = [p for p in old_code if p not in snap["code"]]
        if gone:
            findings.append(f"OFFICE FILE DELETED -- {', '.join(gone[:4])}"
                            f"{f' and {len(gone) - 4} more' if len(gone) > 4 else ''}. "
                            f"Nothing should be removing the build's own source.")
        if len(changed) > 25:
            findings.append(f"OFFICE CODE CHANGED -- {len(changed)} source files differ from the "
                            f"baseline. That is the size of a work session, not an edit.")
        elif changed:
            findings.append(f"OFFICE CODE CHANGED -- {', '.join(changed[:5])}"
                            f"{f' and {len(changed) - 5} more' if len(changed) > 5 else ''}.")

        # The baseline moves forward on the CODE half only: Claude edits this
        # build constantly on his say-so, and re-reporting the same edit every
        # 15 minutes would train him to ignore the whole list. Startup,
        # admins and executables deliberately do NOT auto-accept -- those he
        # has to bless, because those are the ones that matter.
        if changed or gone:
            base["code"] = snap["code"]
            _save(base)
    except Exception as e:  # noqa: BLE001
        findings.append(f"HOST CHECK ERROR -- {type(e).__name__}: {e}")
    return findings[:max_findings]


def summary() -> str:
    base = _load()
    if not base:
        return "host watch: no baseline yet"
    return (f"host watch: baseline {base.get('taken')}, "
            f"{len(base.get('startup') or {})} startup entries, "
            f"{len(base.get('executables') or {})} executables tracked")
