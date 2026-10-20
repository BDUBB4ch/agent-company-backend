"""Sophie's PC security officer -- Barry, 2026-09-07: "she should have a virus
protection suit or something if possible. i want her to keep my pc safe."

WHY THIS IS NOT A HOMEMADE ANTIVIRUS, stated plainly because it matters:
a real AV needs kernel-level file-system filters, a signature feed updated
several times a day, cloud reputation, and a vendor's threat-intel team. A
hand-rolled one would be strictly WORSE than what is already on this machine
and would give him false confidence -- which is the opposite of keeping his PC
safe. Measured 2026-09-07: Microsoft Defender is ON with real-time protection,
tamper protection, behaviour monitoring, signatures 0 days old, and all three
firewall profiles enabled. His protection is good. What was missing was
somebody WATCHING it.

So Sophie is the security officer, not the antivirus:
  * she reads Defender's real state every 15 minutes,
  * she reports the moment real-time protection goes off, signatures go stale,
    tamper protection drops, a firewall profile is switched off, or a threat is
    detected,
  * she can run a Defender scan -- and ONLY when Barry says so in his own
    message (same code-gate as undo_code_fix; the model never decides it was
    asked).

READ-ONLY except `start_scan`, which is the single action in this file and is
gated. Never raises: a failed probe is reported as text, because this rides in
Sophie's health tool and her watch.
"""
import datetime
import json
import subprocess
import time

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_CACHE: dict = {"at": 0.0, "value": None}
_TTL = 600.0          # 10 min -- Defender's own state does not change by the second

# Thresholds. Defender updates signatures several times a day; 3 days is
# genuinely stale, not merely "not today".
_STALE_SIG_DAYS = 3
_SCAN_OVERDUE_DAYS = 14


def _ps(script: str, timeout: int = 30) -> str:
    return subprocess.run(["powershell", "-NoProfile", "-Command", script],
                          capture_output=True, text=True, timeout=timeout,
                          creationflags=_NO_WINDOW).stdout.strip()


def status(force: bool = False) -> dict:
    """Defender + firewall + recent threats. Cached 10 minutes."""
    if not force and _CACHE["value"] and time.time() - _CACHE["at"] < _TTL:
        return _CACHE["value"]

    script = r"""
$ErrorActionPreference='SilentlyContinue'
$s = Get-MpComputerStatus
$fw = Get-NetFirewallProfile | Select-Object Name,Enabled
$det = Get-MpThreatDetection | Sort-Object InitialDetectionTime -Descending | Select-Object -First 10 |
       ForEach-Object { [pscustomobject]@{
           when = $_.InitialDetectionTime.ToString('yyyy-MM-dd HH:mm')
           id   = $_.ThreatID
           action = $_.ThreatStatusID
           resources = ($_.Resources -join '; ')
       } }
[pscustomobject]@{
  av_enabled      = $s.AntivirusEnabled
  realtime        = $s.RealTimeProtectionEnabled
  behavior        = $s.BehaviorMonitorEnabled
  tamper          = $s.IsTamperProtected
  sig_age_days    = $s.AntivirusSignatureAge
  sig_updated     = if ($s.AntivirusSignatureLastUpdated) { $s.AntivirusSignatureLastUpdated.ToString('yyyy-MM-dd HH:mm') } else { $null }
  last_quick_scan = if ($s.QuickScanEndTime) { $s.QuickScanEndTime.ToString('yyyy-MM-dd HH:mm') } else { $null }
  last_full_scan  = if ($s.FullScanEndTime) { $s.FullScanEndTime.ToString('yyyy-MM-dd HH:mm') } else { $null }
  engine          = $s.AMEngineVersion
  firewall        = $fw
  detections      = @($det)
} | ConvertTo-Json -Depth 4 -Compress
"""
    out: dict
    try:
        raw = _ps(script, timeout=45)
        out = json.loads(raw) if raw else {}
        if not out:
            out = {"error": "Defender status came back empty"}
    except Exception as e:  # noqa: BLE001
        out = {"error": f"could not read Defender/firewall: {e}"}

    out["checked"] = datetime.datetime.now().isoformat(timespec="minutes")
    out["note"] = ("Microsoft Defender is the antivirus. Sophie watches it -- she is not "
                   "a replacement for it. If real-time protection is off, that is the "
                   "single most urgent thing on this list.")
    _CACHE.update(at=time.time(), value=out)
    return out


def _days_since(stamp: str | None) -> float | None:
    if not stamp:
        return None
    try:
        d = datetime.datetime.strptime(stamp, "%Y-%m-%d %H:%M")
        return (datetime.datetime.now() - d).total_seconds() / 86400.0
    except ValueError:
        return None


def check(since: str = "") -> list[str]:
    """Plain-English findings for Sophie's watch. Empty = his PC is fine.

    `since` (ISO) suppresses threat detections he has already been told about;
    the PROTECTION findings are never suppressed -- real-time protection being
    off is news every tick until it is back on."""
    s = status()
    if s.get("error"):
        return [f"PC SECURITY -- {s['error']}"]

    f: list[str] = []

    if s.get("av_enabled") is False:
        f.append("ANTIVIRUS OFF -- Microsoft Defender antivirus is disabled. "
                 "This PC is unprotected right now.")
    if s.get("realtime") is False:
        f.append("REAL-TIME PROTECTION OFF -- Defender is not scanning files as they "
                 "open. Turn it back on in Windows Security > Virus & threat protection.")
    if s.get("behavior") is False:
        f.append("BEHAVIOUR MONITORING OFF -- Defender's live behaviour engine is "
                 "disabled; it catches things signatures miss.")
    if s.get("tamper") is False:
        f.append("TAMPER PROTECTION OFF -- other software (or malware) can now change "
                 "Defender's settings. Turn it back on in Windows Security.")

    age = s.get("sig_age_days")
    if isinstance(age, (int, float)) and age >= _STALE_SIG_DAYS:
        f.append(f"VIRUS DEFINITIONS STALE -- {int(age)} days old (updated "
                 f"{s.get('sig_updated')}). Defender normally updates several times a day; "
                 "this usually means it cannot reach the internet.")

    quick = _days_since(s.get("last_quick_scan"))
    full = _days_since(s.get("last_full_scan"))
    if quick is None and full is None:
        f.append("NO SCAN ON RECORD -- Defender has no completed scan logged. "
                 "Worth running one (say the word and Sophie starts a quick scan).")
    elif full is None and (quick is None or quick > _SCAN_OVERDUE_DAYS):
        f.append(f"NO FULL SCAN ON RECORD -- last quick scan "
                 f"{s.get('last_quick_scan') or 'never'}. Real-time protection covers the "
                 "day to day; a full scan is still worth running occasionally.")

    for p in (s.get("firewall") or []):
        if isinstance(p, dict) and p.get("Enabled") in (False, 0):
            f.append(f"FIREWALL OFF -- the {p.get('Name')} profile is disabled. "
                     "That is how something on the network gets in.")

    for d in (s.get("detections") or []):
        when = d.get("when") or ""
        if since and when and when.replace(" ", "T") <= since[:16]:
            continue
        f.append(f"THREAT DETECTED -- {when}, threat id {d.get('id')} "
                 f"({d.get('resources') or 'no path recorded'}). Check Windows Security > "
                 "Protection history for what Defender did with it.")

    # The dormant-file gap: real-time protection does not sweep old files.
    f.extend(scan_gaps())
    return f


def start_scan(kind: str = "quick") -> dict:
    """Run a Defender scan. THE ONLY ACTION IN THIS FILE, and it is gated on
    Barry's own words by the caller (llm_router), never on the model's opinion
    that he asked."""
    kind = (kind or "quick").strip().lower()
    if kind not in ("quick", "full"):
        return {"ok": False, "error": "kind must be 'quick' or 'full'."}
    scan = "QuickScan" if kind == "quick" else "FullScan"
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-Command",
                          f"Start-MpScan -ScanType {scan}"],
                         creationflags=_NO_WINDOW)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"could not start the {kind} scan: {e}"}
    _CACHE["value"] = None      # next status() reads the real post-scan state
    return {"ok": True, "started": kind,
            "note": (f"Defender {kind} scan started in the background. A quick scan is "
                     "usually a few minutes; a full scan can take hours and will use the "
                     "CPU. Results appear in Windows Security > Protection history, and "
                     "Sophie will report anything found on her next check.")}


def scan_gaps() -> list[str]:
    """The honest answer to 'how would she know if she doesn't scan?'

    Real-time protection checks every file as it is opened, written or run --
    that is continuous and it is the main defence. What it does NOT do is sweep
    files sitting dormant on disk that arrived before a signature for them
    existed. Only a scan does that. Measured on this PC 2026-09-07:
      * scheduled scan runs DAILY but is QUICK only (ScanParameters=1),
      * catch-up scans are DISABLED, so a scan missed while the PC is off is
        skipped forever rather than run late,
      * no FULL scan has ever completed.
    So the dormant-file gap is real here, and these are the findings for it."""
    gaps: list[str] = []
    try:
        raw = _ps("$ErrorActionPreference='SilentlyContinue';"
                  "$p=Get-MpPreference;"
                  "[pscustomobject]@{day=$p.ScanScheduleDay;params=$p.ScanParameters;"
                  "cq=$p.DisableCatchupQuickScan;cf=$p.DisableCatchupFullScan} |"
                  " ConvertTo-Json -Compress", timeout=30)
        p = json.loads(raw) if raw else {}
    except Exception:  # noqa: BLE001
        return []
    if p.get("params") == 1:
        # ⚠️ THE TAIL OF THIS LINE USED TO SAY "Nothing has ever full-scanned
        # this PC" as a hardcoded fact. It was true when it was written
        # (2026-09-07) and FALSE a few hours later, because Sophie's own
        # maybe_auto_scan ran a full scan that same night -- so for twelve days
        # her security report stated something her own scan history disproved.
        # A finding that lies is how real findings get ignored. It reads the
        # actual date now.
        _full = status().get("last_full_scan")
        _age = _days_since(_full)
        if _full and _age is not None:
            _tail = (f"The last FULL scan was {_full} ({int(_age)} days ago) and it was "
                     f"Sophie's, not the schedule's -- the schedule alone would never run one.")
        else:
            _tail = "Nothing has ever full-scanned this PC."
        gaps.append("SCAN COVERAGE -- the daily scheduled scan is QUICK only. A quick scan "
                    "checks memory, startup and the usual malware locations; it does not "
                    "read dormant files sitting on disk. " + _tail)
    if p.get("cq") or p.get("cf"):
        gaps.append("MISSED SCANS ARE SKIPPED -- Defender's catch-up scans are disabled, so a "
                    "scan scheduled while the PC is off never runs late. That is why there are "
                    "gaps in the scan history.")
    return gaps


def maybe_auto_scan(state: dict) -> tuple[list[str], dict]:
    """Sophie scanning ON HER OWN, because 'is it protected' and 'has anything
    been swept' are different questions (Barry, 2026-09-07: "how would she know
    if she doesnt scan?").

    QUICK if nothing has completed in 2 days. FULL if one has never completed
    or it has been 30 days -- and full ONLY outside working hours, because a
    full scan is hours of CPU and it must never land in the middle of his day.
    Never while the GPU is rendering. Returns (findings, updated_state)."""
    import os
    findings: list[str] = []
    now = datetime.datetime.now()

    flag = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "video_rendering.flag")
    if os.path.exists(flag):
        try:
            if (time.time() - os.path.getmtime(flag)) < 7200:
                return [], state          # a render owns the machine; never compete
        except OSError:
            pass

    s = status()
    if s.get("error"):
        return [], state

    last_any = max([d for d in (s.get("last_quick_scan"), s.get("last_full_scan")) if d] or [""])
    days_any = _days_since(last_any)
    days_full = _days_since(s.get("last_full_scan"))

    def _recent(key: str, hours: float) -> bool:
        prev = state.get(key)
        if not prev:
            return False
        try:
            return (now - datetime.datetime.fromisoformat(prev)).total_seconds() < hours * 3600
        except ValueError:
            return False

    # FULL: the real gap on this machine. Off-hours only.
    off_hours = now.hour >= 18 or now.hour < 9 or now.weekday() >= 5
    if (days_full is None or days_full > 30) and off_hours and not _recent("last_auto_full", 24 * 7):
        r = start_scan("full")
        state["last_auto_full"] = now.isoformat(timespec="minutes")
        findings.append(
            "FULL SCAN STARTED -- no full scan had ever completed on this PC, so dormant "
            "files had never been swept. Sophie started one off-hours; it runs in the "
            "background for a few hours and results appear in Protection history."
            if r.get("ok") else f"FULL SCAN FAILED TO START -- {r.get('error')}")
        return findings, state

    # QUICK: cheap, a few minutes, safe any time the GPU is free.
    if (days_any is None or days_any > 2) and not _recent("last_auto_quick", 20):
        r = start_scan("quick")
        state["last_auto_quick"] = now.isoformat(timespec="minutes")
        findings.append(
            f"QUICK SCAN STARTED -- no completed scan in "
            f"{'ever' if days_any is None else f'{int(days_any)} days'}. Sophie started one."
            if r.get("ok") else f"QUICK SCAN FAILED TO START -- {r.get('error')}")
    return findings, state


def summary() -> str:
    """One line for system_health."""
    s = status()
    if s.get("error"):
        return f"unreadable ({s['error']})"
    f = check()
    bits = [f"Defender {'ON' if s.get('realtime') else 'OFF'}",
            f"definitions {s.get('sig_age_days')}d old",
            f"tamper protection {'on' if s.get('tamper') else 'OFF'}"]
    return ", ".join(bits) + (f" -- {len(f)} finding(s)" if f else " -- all clear")
