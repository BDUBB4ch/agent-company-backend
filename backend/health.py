"""System health for Sophie's system_health tool (Phase A of the coder
upgrade, Barry's "go" 2026-08-28).

READ-ONLY by construction: this module contains no write verbs at all --
socket probes, DB reads, string building. Same pattern as store.py's
read-only guarantee. Not offline-stripped: everything here is localhost.
"""
import datetime
import json
import os
import socket

import memory
import tracing
from agents import AGENTS, PINNED_SKILLS

# Port map mirrors the components table in CLAUDE.md. The backend itself is
# deliberately absent -- if this code is running, port 8420 is answering.
_SERVICES = [
    ("Ollama (chat models)", 11434),
    ("Bonsai llama-server", 8811),
    ("ComfyUI (image/video)", 8188),
    ("Dashboard web server", 8765),
]

# Thresholds from scripts/office_health.py: Elliot produced word salad at
# ~220K always-on; 140K is the warn line, 190K the fail line.
_WARN_CHARS = 140_000
_FAIL_CHARS = 190_000


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.5):
            return True
    except OSError:
        return False


_CLIENT_ERRORS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "client_errors.jsonl")


def dashboard_errors(since: str = "", hours: float = 24.0, max_groups: int = 15) -> list[dict]:
    """Browser-side failures reported by AgentDashboard/client-errors.js,
    grouped by deck + kind + message, newest first. `since` (ISO) wins over
    `hours` when given. Read-only; missing file = no errors."""
    if not os.path.exists(_CLIENT_ERRORS_PATH):
        return []
    if not since:
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
        since = cutoff.isoformat()
    groups: dict[tuple, dict] = {}
    try:
        with open(_CLIENT_ERRORS_PATH, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if (r.get("received") or r.get("ts") or "") <= since:
                    continue
                key = (r.get("deck"), r.get("kind"), (r.get("message") or "")[:160])
                g = groups.setdefault(key, {
                    "deck": r.get("deck"), "kind": r.get("kind"),
                    "message": r.get("message"), "count": 0,
                    "last": r.get("received") or r.get("ts"),
                    "where": " ".join(str(r.get(k)) for k in ("source", "line") if r.get(k)) or None,
                })
                g["count"] += 1
                g["last"] = max(g["last"] or "", r.get("received") or r.get("ts") or "")
    except OSError:
        return []
    out = sorted(groups.values(), key=lambda g: g["last"] or "", reverse=True)
    return out[:max_groups]


_NET_CACHE = {"at": 0.0, "value": None}
_NET_TTL = 300.0   # five minutes -- a probe per message would be its own outage


def internet_status(force: bool = False) -> dict:
    """CAN THE OFFICE REACH THE INTERNET RIGHT NOW (2026-09-02, Barry: "will
    they tell me if they cant reach the internet?"). Two cheap TCP connects
    (Cloudflare DNS on 443 and duckduckgo.com on 443), cached five minutes.
    Read by the presence block (every agent, every message), system_health,
    and Sophie's watch. Offline Mode is a separate, deliberate switch."""
    import time as _t
    if not force and _NET_CACHE["value"] is not None and _t.time() - _NET_CACHE["at"] < _NET_TTL:
        return _NET_CACHE["value"]
    ok, detail = False, []
    for host, port in (("1.1.1.1", 443), ("duckduckgo.com", 443)):
        try:
            with socket.create_connection((host, port), timeout=3):
                ok = True
                detail.append(f"{host} reachable")
                break
        except OSError as e:
            detail.append(f"{host}: {e.__class__.__name__}")
    value = {"reachable": ok, "checked": datetime.datetime.now().isoformat(timespec="minutes"),
             "detail": "; ".join(detail)}
    _NET_CACHE.update(at=_t.time(), value=value)
    return value


_MACHINE_CACHE: dict = {"at": 0.0, "value": None}


def machine_health(force: bool = False) -> dict:
    """THE PC ITSELF (2026-09-04, Barry: "you are supposed to take care of me
    and make sure my stuff is all good. That includes my builds and pc").
    He woke to a crashed machine and was told "standby" from a boot time;
    the System log said Kernel-Power 41 / bugcheck 0x3B -- the third blue
    screen in a month, every one under GPU load, and nobody was watching.
    Read-only, cached 10 min (two PowerShell calls). Reports: the last
    unexpected shutdown with its bugcheck code, minidumps on disk, free space
    on C: and D:, and the GPU driver version/date. Never raises -- a failed
    read is reported as text, because this rides in Sophie's health tool."""
    import time as _t, shutil, subprocess, json as _json
    if not force and _MACHINE_CACHE["value"] and _t.time() - _MACHINE_CACHE["at"] < 600:
        return _MACHINE_CACHE["value"]
    out: dict = {}
    try:
        for drive in ("C:\\", "D:\\"):
            u = shutil.disk_usage(drive)
            out[f"disk_{drive[0]}"] = f"{u.free / 1e9:.0f} GB free of {u.total / 1e9:.0f} GB" + (
                "  !! LOW" if u.free < 20e9 else "")
    except OSError as e:
        out["disk"] = f"unreadable: {e}"
    ps = r"""
$ErrorActionPreference='SilentlyContinue'
$ev = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-Kernel-Power'; Id=41} -MaxEvents 1
$code = $null; $when = $null
if ($ev) { $when = $ev.TimeCreated.ToString('yyyy-MM-dd HH:mm'); $code = (([xml]$ev.ToXml()).Event.EventData.Data | ? { $_.Name -eq 'BugcheckCode' }).'#text' }
$dumps = Get-ChildItem C:\Windows\Minidump -Filter *.dmp | Sort-Object LastWriteTime | Select-Object -Last 5 | % { $_.LastWriteTime.ToString('yyyy-MM-dd HH:mm') }
$gpu = Get-CimInstance Win32_VideoController | Select-Object -First 1
[pscustomobject]@{ last_unexpected_shutdown=$when; bugcheck_code=$code; minidumps=@($dumps); gpu=$gpu.Name; driver=$gpu.DriverVersion; driver_date=$gpu.DriverDate.ToString('yyyy-MM-dd') } | ConvertTo-Json -Compress
"""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True,
                           text=True, timeout=25, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        info = _json.loads(r.stdout.strip() or "{}")
        code = info.get("bugcheck_code")
        out["last_unexpected_shutdown"] = (
            f"{info.get('last_unexpected_shutdown')} -- bugcheck {code} "
            f"({'0x%X' % int(code) if str(code).isdigit() else code}); a BLUE SCREEN / hard reset, "
            "not sleep and not a clean reboot" if info.get("last_unexpected_shutdown") else "none on record")
        dumps = info.get("minidumps") or []
        out["minidumps"] = (f"{len(dumps)} on disk, newest {dumps[-1]} (C:\\Windows\\Minidump, admin needed to read)"
                            if dumps else "none")
        out["gpu_driver"] = f"{info.get('gpu')} driver {info.get('driver')} ({info.get('driver_date')})"
    except Exception as e:  # noqa: BLE001
        out["events"] = f"unreadable: {e}"
    out["note"] = ("An unexpected shutdown newer than the last one Barry knows about is a "
                   "finding: tell him the time and the bugcheck code, and that the minidump "
                   "needs his admin copy to be read. Do not call a crash 'standby'.")
    _MACHINE_CACHE.update(at=_t.time(), value=out)
    return out


def _updates_line() -> str:
    try:
        import updates
        return updates.summary_line()
    except Exception as e:  # noqa: BLE001
        return f"updates: unavailable ({e})"


def _security_section() -> dict:
    """Sophie's standing security posture -- exposed ports, banned services in
    the source, the office browser profile, outbound host drift. Never raises:
    a broken security check must not break system_health."""
    try:
        import security_watch
        return security_watch.status()
    except Exception as e:  # noqa: BLE001
        return {"clean": False, "findings": [f"security check could not run: {e}"],
                "summary": "security check unavailable"}


def _pc_protection_line() -> str:
    """Defender + firewall in one line -- Sophie watches the antivirus, she is
    not one. Never raises."""
    try:
        import pc_security
        return pc_security.summary()
    except Exception as e:  # noqa: BLE001
        return f"unreadable ({e})"


def _bonsai_server_errors(n: int = 5) -> list[str] | str:
    """The last n error lines llama-server wrote (its ' E ' log level),
    from the tail of data/bonsai_server.log. Read-only, tail only."""
    try:
        import bonsai_llm
        path = bonsai_llm._SERVER_LOG_PATH
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - 200_000))
            tail = fh.read().decode("utf-8", errors="replace")
        errs = [ln.strip() for ln in tail.splitlines() if " E " in ln[:32]]
        return errs[-n:] if errs else "no errors in the server log tail"
    except Exception as e:  # noqa: BLE001
        return f"server log unreadable: {e}"


def bonsai_events(n: int = 12, hours: int = 24) -> list[str] | str:
    """Bonsai's own health events -- failures, circuit trips, resets.

    2026-09-17: these were bare print()s and the backend's stdout is captured
    nowhere, so the breaker could put nine seats on the 9b with no record that
    it happened. That invisibility is why "the 27B returns empty responses"
    kept coming back unsolved. If this list shows repeated trips, the
    orchestration is failing, not the model.
    """
    try:
        import bonsai_llm
        path = bonsai_llm._EVENTS_PATH
        if not os.path.exists(path):
            return "no Bonsai health events recorded"
        cutoff = (datetime.datetime.now() - datetime.timedelta(hours=hours)
                  ).strftime("%Y-%m-%d %H:%M:%S")
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = [ln.strip() for ln in fh if ln.strip() and ln[:19] >= cutoff]
        return lines[-n:] if lines else f"no Bonsai failures or trips in the last {hours}h"
    except Exception as e:  # noqa: BLE001
        return f"events log unreadable: {e}"


def system_health() -> dict:
    backend, model = memory.get_active_generation()
    overrides = memory.get_agent_model_overrides()

    services = []
    for label, port in _SERVICES:
        up = _port_open(port)
        note = ""
        if not up and port == 8811:
            note = " (normal when idle -- it starts on demand and is evicted for renders)"
        if not up and port == 8188:
            note = " (normal when idle -- started on demand for image/video work)"
        services.append(f"{label} [:{port}]: {'UP' if up else 'DOWN'}{note}")

    loads = []
    import agents as _agents
    for aid, office, _name in _agents.all_seats():                 # hires too (2026-10-10)
        try:
            brain = len(memory.brain_context_block(office))
            pins = len(memory.pinned_skills_block(office, PINNED_SKILLS.get(aid, [])))
        except Exception as e:  # noqa: BLE001 -- a broken shelf should show, not crash
            loads.append(f"{office}: ERROR reading brain ({e})")
            continue
        total = brain + pins
        flag = " !! OVER FAIL LINE" if total > _FAIL_CHARS else (
            " ! over warn line" if total > _WARN_CHARS else "")
        loads.append(f"{office}: {total:,} chars always-on"
                     f" (brain {brain:,} + pins {pins:,}){flag}")

    failures = tracing.query_recent_traces(only_failures=True, limit=10)
    dash = dashboard_errors()
    try:
        import watch
        watch_status = watch.status()
    except Exception as e:  # noqa: BLE001
        watch_status = {"error": f"watch status unavailable: {e}"}

    return {
        "model_backend": f"{backend} / {model}",
        "runtime_model_overrides": overrides or "none -- every seat follows the global or the hardcoded map",
        "offline_mode": memory.is_offline_mode(),
        "internet": internet_status(),
        "services": services,
        "always_on_load_per_agent": loads,
        "load_thresholds": f"warn {_WARN_CHARS:,} / fail {_FAIL_CHARS:,} chars",
        "recent_verified_failures": failures if failures else "none in recent traces",
        # 2026-09-14: Sophie could see "Bonsai returned 400" and not WHY --
        # the reason lives only in llama-server's own log. Its last error
        # lines ride here ("request (61233 tokens) exceeds the available
        # context size (49152)" is a diagnosis; "400" is not).
        "bonsai_server_last_errors": _bonsai_server_errors(),
        # 2026-09-17: the ORCHESTRATION side -- trips and fallbacks, which the
        # server log cannot show because nothing was wrong with the server.
        "bonsai_health_events": bonsai_events(),
        # SOPHIE'S EYES ON THE DASHBOARD (2026-09-02): every deck reports
        # JavaScript errors, failed script loads and console.error calls to
        # /api/client-errors. Last 24h, grouped.
        "recent_dashboard_errors": dash if dash else "none reported by any deck in the last 24h",
        # What her own background watch (watch.py) last found -- so she can
        # say "my watch flagged X at 2:15" instead of rediscovering it.
        "my_watch": watch_status,
        # THE MACHINE (2026-09-04): crashes, dumps, disk, driver -- see machine_health.
        "machine": machine_health(),
        # Barry, 2026-09-07: "allow sophie to do security at all time".
        "security": _security_section(),
        "pc_protection": _pc_protection_line(),
        # THE UPDATE BOARD (2026-09-06): one line; check_updates has the detail.
        "updates": _updates_line(),
        "note": ("This is a live read-only snapshot. If something is DOWN that "
                 "shouldn't be, or a load is over a line, report it to Barry "
                 "in plain words -- do not attempt any fix without his OK."),
    }
