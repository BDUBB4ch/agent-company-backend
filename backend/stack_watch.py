"""The supervisor and the card -- two things nobody was watching (2026-10-09).

Barry: "whatever it is, she should be able to fix it, right, if not show her how and make it her thing to watch as
well. she needs to monitor shit."

1. THE STACK WATCHDOG (scripts/stack_watchdog.ps1, launched hidden at Windows login by the Startup folder's
   "Barrys AI Stack Watchdog.bat"). It revives Ollama / backend / dashboard / SearXNG every 45 s -- and nothing
   revives IT. It died twice on 2026-10-09 (last log lines 09:36 and 13:10, process simply gone, no error), so
   each backend restart left the office dark until a human relaunched it. Sophie's 15-minute watch now checks the
   process and relaunches it the same way the .bat does -- a mechanical, simple, vital fix (the supervisor is the
   thing that keeps everything else alive) -- and reports it as a finding so the pattern is visible.
2. GPU DRIVER RESETS. Windows logs a LiveKernelEvent (Windows Error Reporting event 1001, P1 141 or 0xA1000001
   via the AMD driver's amdfendr live dump) when the display driver times out and recovers. One hit at 12:18 on
   2026-10-09 during an agent's self-picture render; the office rode through it (a time ceiling and a fallback) but
   he had no idea. His PC-care rule: hard hangs under GPU load = suspect clocks/driver first. These are now
   findings with the time and what was on the card.

Pure reads except the one relaunch. Never raises -- the watch loop lives on.
"""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA = os.path.join(_ROOT, "data")
WATCHDOG_PS1 = os.path.join(_ROOT, "scripts", "stack_watchdog.ps1")
WATCHDOG_LOG = os.path.join(_DATA, "watchdog.log")
WATCHDOG_BAT = os.path.join(os.environ.get("APPDATA", r"C:\Users\Owner\AppData\Roaming"),
                            "Microsoft", "Windows", "Start Menu", "Programs", "Startup",
                            "Barrys AI Stack Watchdog.bat")
_LOG = os.path.join(_DATA, "stack_watch.log")
_STATE = os.path.join(_DATA, "stack_watch_state.json")
_NO_WINDOW = 0x08000000


def _log(msg: str) -> None:
    try:
        with open(_LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}\n")
    except OSError:
        pass


def _ps(script: str, timeout: int = 40) -> str:
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                             capture_output=True, text=True, timeout=timeout, creationflags=_NO_WINDOW)
        return (out.stdout or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _state() -> dict:
    try:
        with open(_STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(st: dict) -> None:
    try:
        with open(_STATE, "w", encoding="utf-8") as f:
            json.dump(st, f, indent=1)
    except OSError:
        pass


# ------------------------------------------------------------------ watchdog ---
def watchdog_pids() -> list[int]:
    """PIDs of live stack_watchdog.ps1 processes. The query's own PowerShell carries the file name in its
    command line too, so it is excluded by the word Get-CimInstance (bit us twice on 10-09)."""
    raw = _ps("Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" | Where-Object { "
              "$_.CommandLine -like '*stack_watchdog.ps1*' -and $_.CommandLine -notlike '*Get-CimInstance*' } | "
              "ForEach-Object { $_.ProcessId }")
    return [int(x) for x in raw.split() if x.strip().isdigit()]


TASK_NAME = "Barrys AI Stack Watchdog"      # the logon task (2026-10-09, Barry: "set up the logon task") -- it restarts
                                            # the watchdog itself if it ever exits; the Startup .bat is retired to
                                            # data/backup_retired_launchers_2026-10-09/ and only used if the task is gone


def relaunch_watchdog() -> str:
    """Start it the way Windows does now: the logon task (supervised). Falls back to the retired .bat only if the
    task does not exist. Returns a plain-English result."""
    how = ""
    if _ps(f"(Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue).TaskName", timeout=20):
        _ps(f"Start-ScheduledTask -TaskName '{TASK_NAME}'", timeout=20)
        how = f"via the logon task '{TASK_NAME}'"
    else:
        bat = next((p for p in (WATCHDOG_BAT,
                                os.path.join(_DATA, "backup_retired_launchers_2026-10-09", "Barrys AI Stack Watchdog.bat"))
                    if os.path.isfile(p)), "")
        if not bat:
            return f"could not relaunch: the logon task '{TASK_NAME}' is missing and so is the old Startup launcher"
        _ps(f"Start-Process -FilePath '{bat}' -WindowStyle Hidden", timeout=20)
        how = f"via the old launcher (the logon task '{TASK_NAME}' is MISSING -- tell Barry)"
    time.sleep(5)
    pids = watchdog_pids()
    return f"relaunched {how} (pid {pids[0]})" if pids else f"relaunch attempted {how} but no watchdog process appeared"


def check_watchdog(st: dict) -> list[str]:
    pids = watchdog_pids()
    if pids:
        if st.get("watchdog_missing_since"):
            st.pop("watchdog_missing_since", None)
        return []
    today = datetime.date.today().isoformat()
    deaths = st.get("watchdog_deaths") or {}
    deaths[today] = int(deaths.get(today, 0)) + 1
    st["watchdog_deaths"] = {k: v for k, v in deaths.items() if k >= (datetime.date.today()
                                                                      - datetime.timedelta(days=7)).isoformat()}
    last_line = ""
    try:
        with open(WATCHDOG_LOG, encoding="utf-8", errors="ignore") as f:
            lines = f.read().splitlines()
        last_line = lines[-1] if lines else ""
    except OSError:
        pass
    result = relaunch_watchdog()
    _log(f"watchdog was DEAD (last log line: {last_line!r}) -> {result}")
    return [f"STACK WATCHDOG WAS DEAD -- the supervisor that revives the backend/Ollama/dashboard was not "
            f"running (its last log line: {last_line or 'none'}); {result}. Death #{deaths[today]} today; "
            f"it has no supervisor of its own (Startup .bat only). If this repeats, a logon task that restarts "
            f"it on exit is the fix -- Barry's call."]


# ---------------------------------------------------------------- GPU resets ---
def gpu_driver_events(hours: float = 24) -> list[dict]:
    """LiveKernelEvent reports (WER 1001) in the Application log: the display driver timed out and reset."""
    script = (
        "$t=(Get-Date).AddHours(-%s); Get-WinEvent -FilterHashtable @{LogName='Application'; Id=1001; StartTime=$t} "
        "-ErrorAction SilentlyContinue | Where-Object { $_.Message -like '*LiveKernelEvent*' } | "
        "ForEach-Object { $m=$_.Message; $p1=''; if($m -match 'P1:\\s*(\\S+)'){ $p1=$matches[1] }; "
        "$b=''; if($m -match 'Fault bucket ([^,]*),'){ $b=$matches[1] }; "
        "[pscustomobject]@{t=$_.TimeCreated.ToString('yyyy-MM-dd HH:mm'); p1=$p1; bucket=$b} } | "
        "ConvertTo-Json -Compress" % hours)
    raw = _ps(script, timeout=60)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    rows = data if isinstance(data, list) else [data]
    out, seen = [], set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        key = (r.get("t"), r.get("p1"))
        if key in seen:
            continue
        seen.add(key)
        out.append({"time": r.get("t", ""), "code": r.get("p1", ""), "bucket": (r.get("bucket") or "")[:80]})
    return out


def _office_line_near(when: str) -> str:
    """What the watchdog saw the office doing nearest that minute ('office: GPU render ...')."""
    try:
        with open(WATCHDOG_LOG, encoding="utf-8", errors="ignore") as f:
            lines = [ln for ln in f.read().splitlines() if " office: " in ln]
    except OSError:
        return ""
    best, bt = "", None
    for ln in lines:
        stamp = ln[:16]
        if stamp <= when and (bt is None or stamp > bt):
            best, bt = ln, stamp
    return best.split(" office: ", 1)[1] if " office: " in best else ""


def _minutes(stamp: str) -> int:
    try:
        d = datetime.datetime.strptime(stamp, "%Y-%m-%d %H:%M")
        return int(d.timestamp() // 60)
    except ValueError:
        return 0


def check_gpu(st: dict) -> list[str]:
    """One finding per BURST (events within 10 minutes of each other): a single reset storm logged seven events
    on 10-09 (12:18-12:22) and would have been seven findings."""
    seen = set(st.get("gpu_events_seen") or [])
    new = []
    for ev in sorted(gpu_driver_events(24), key=lambda e: e["time"]):
        key = f"{ev['time']}|{ev['code']}"
        if key in seen:
            continue
        seen.add(key)
        new.append(ev)
    st["gpu_events_seen"] = sorted(seen)[-200:]
    bursts: list[list[dict]] = []
    for ev in new:
        if bursts and _minutes(ev["time"]) - _minutes(bursts[-1][-1]["time"]) <= 10:
            bursts[-1].append(ev)
        else:
            bursts.append([ev])
    findings = []
    for b in bursts:
        first, last = b[0]["time"], b[-1]["time"]
        when = first if first == last else f"{first} to {last[-5:]}"
        codes = sorted({e["code"] for e in b if e["code"]})
        bucket = next((e["bucket"] for e in b if e["bucket"]), "")
        doing = _office_line_near(first)
        findings.append(
            f"GPU DRIVER RESET -- {len(b)} LiveKernelEvent(s) {'/'.join(codes) or '?'} at {when}: the AMD display "
            f"driver timed out and recovered ({bucket or 'no bucket'}). The office was doing: {doing or 'unknown'}. "
            f"The PC did not crash. Barry's rule: a hang under GPU load = suspect clocks/driver first; clocks are "
            f"at stock. Note it, correlate with what was on the card, and tell him -- change nothing on the card.")
    return findings


def check_gpu_device(st: dict) -> list[str]:
    """2026-10-10: after a reboot the RX 9070 XT came up DISABLED (Device Manager code 22) and nothing said so --
    Bonsai loaded on the CPU ("no ROCm-capable device"), ~3 tok/s, Elliot timed out for an hour. Reports the card's
    state when it is not OK, and once more when it comes back. Changes nothing on the machine."""
    out = _ps("$d = Get-PnpDevice -Class Display -ErrorAction SilentlyContinue | Where-Object { $_.FriendlyName -match "
              "'Radeon' } | Select-Object -First 1; if ($d) { $d.FriendlyName + '|' + $d.Status + '|' + $d.Problem }")
    line = (out or "").strip().splitlines()[-1] if (out or "").strip() else ""
    if "|" not in line:
        return []                      # PowerShell gave nothing usable: unknown is not an alarm
    name, status, problem = (line.split("|") + ["", "", ""])[:3]
    state = f"{status}|{problem}"
    prev = st.get("gpu_device_state")
    st["gpu_device_state"] = state
    if status == "OK":
        return [f"GPU BACK -- {name} is OK again (was {prev})."] if prev and not prev.startswith("OK") else []
    if state == prev:
        return []
    return [f"GPU OFF -- {name} is {status} ({problem}). Bonsai cannot use the card and runs on the CPU at ~3 tok/s "
            f"(every seat crawls and times out). Tell Barry now: Device Manager > Display adapters > enable it; a "
            f"code 31 right after enabling needs one reboot. Then restart Bonsai. Change nothing on the card yourself."]


# ------------------------------------------------------------------ entry ---
def check() -> list[str]:
    """Called from watch.check() every tick. Never raises."""
    st = _state()
    findings: list[str] = []
    for fn in (check_watchdog, check_gpu, check_gpu_device):
        try:
            findings.extend(fn(st))
        except Exception as e:  # noqa: BLE001
            findings.append(f"stack check {fn.__name__} could not run: {e}")
    _save(st)
    return findings


def status() -> dict:
    st = _state()
    return {"watchdog_pids": watchdog_pids(), "watchdog_deaths_by_day": st.get("watchdog_deaths") or {},
            "gpu_driver_resets_24h": gpu_driver_events(24)}
