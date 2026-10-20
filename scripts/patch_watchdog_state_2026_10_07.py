r"""One-off patch (2026-10-07, Barry: "make the watchdog know when a video is being made or something. dont just
wait for it to fail, make it know whats going on"): /api/ping reports the office's live state; the watchdog logs it
on change and holds off a kill while a video is building/rendering."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def patch(path, pairs):
    t = open(path, encoding="utf-8").read()
    for a, b in pairs:
        assert t.count(a) == 1, (path, a[:60])
        t = t.replace(a, b)
    open(path, "w", encoding="utf-8").write(t)
    print("ok", os.path.basename(path))


patch(os.path.join(ROOT, "backend", "activity.py"), [(
r'''def snapshot() -> dict:''',
r'''def busy_line() -> dict:
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


def snapshot() -> dict:''')])

patch(os.path.join(ROOT, "backend", "main.py"), [(
r'''    return {"ok": True, "t": time.time()}''',
r'''    try:
        state = activity.busy_line()
    except Exception:  # noqa: BLE001 -- liveness never fails on a status detail
        state = {"busy": "?", "key": "?"}
    return {"ok": True, "t": time.time(), **state}''')])

patch(os.path.join(ROOT, "scripts", "stack_watchdog.ps1"), [
(r'''function Alive($url) {''',
r'''# 2026-10-07 (Barry: "make the watchdog know when a video is being made ... make it know whats going on"):
# /api/ping also says what the office is doing (who is writing, what is building). Returns $null when it did not
# answer, else the state object (.busy with times, .key without).
function PingState($url) {
    try {
        $r = Invoke-WebRequest -Uri $url -TimeoutSec 15 -UseBasicParsing
        if ($r.StatusCode -ne 200) { return $null }
        return ($r.Content | ConvertFrom-Json)
    } catch { return $null }
}
function VideoInProgress() {
    return (Test-Path "C:\Users\Owner\Desktop\AgentCompanyBackend\data\reel_building.flag") -or
           (Test-Path "C:\Users\Owner\Desktop\AgentCompanyBackend\data\video_rendering.flag")
}

function Alive($url) {'''),
(r'''$backendStrikes = 0
$dashStrikes = 0
$STRIKES_BEFORE_KILL = 3
''',
r'''$backendStrikes = 0
$dashStrikes = 0
$STRIKES_BEFORE_KILL = 3
$STRIKES_WHILE_VIDEO = 20      # ~15 min of silence before a kill while a video is building/rendering
$lastKey = ""
'''),
(r'''    elseif (-not (Alive "http://127.0.0.1:8420/api/ping")) {
        $backendStrikes++
        Log "Backend held 8420 but did not answer ($backendStrikes/$STRIKES_BEFORE_KILL)"
        if ($backendStrikes -ge $STRIKES_BEFORE_KILL) {
            $owner = PortOwner 8420
            Log "Backend HUNG -- killing pid $owner and restarting"
            if ($owner) { Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue }
            Start-Sleep -Seconds 3
            Start-Process -FilePath $BACKEND_PY -ArgumentList "main.py" -WorkingDirectory $BACKEND_DIR -WindowStyle Hidden
            $backendStrikes = 0
            $acted = $true
        }
    }
    else { $backendStrikes = 0 }''',
r'''    else {
        $state = PingState "http://127.0.0.1:8420/api/ping"
        if ($null -eq $state) {
            $backendStrikes++
            $video = VideoInProgress
            $limit = if ($video) { $STRIKES_WHILE_VIDEO } else { $STRIKES_BEFORE_KILL }
            $why = if ($video) { " -- holding: a video is building/rendering (last seen: $lastKey)" } else { "" }
            Log "Backend held 8420 but did not answer ($backendStrikes/$limit)$why"
            if ($backendStrikes -ge $limit) {
                $owner = PortOwner 8420
                Log "Backend HUNG -- killing pid $owner and restarting"
                if ($owner) { Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue }
                Start-Sleep -Seconds 3
                Start-Process -FilePath $BACKEND_PY -ArgumentList "main.py" -WorkingDirectory $BACKEND_DIR -WindowStyle Hidden
                $backendStrikes = 0
                $acted = $true
            }
        }
        else {
            $backendStrikes = 0
            if ("$($state.key)" -ne $lastKey) {       # log what the office is doing, only when it changes
                Log "office: $($state.busy)"
                $lastKey = "$($state.key)"
            }
        }
    }'''),
])
