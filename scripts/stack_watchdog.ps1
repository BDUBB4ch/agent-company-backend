# Barry's AI Stack Watchdog (2026-07-31) -- the guardian process.
# Runs hidden from Windows login (Startup folder). Every 45s it health-checks
# each vital service and resurrects anything dead. Every action is logged to
# data\watchdog.log. ComfyUI is deliberately NOT supervised -- it starts on
# demand per render by design.
#
# Owner's requirement: "ima need that to never happen again."

$ErrorActionPreference = "SilentlyContinue"

# Singleton: only one watchdog ever runs.
# 2026-09-15: when the previous watchdog is KILLED (not exited cleanly) its
# named mutex is left abandoned, and WaitOne on an abandoned mutex THROWS
# (AbandonedMutexException) instead of returning true. With the script's
# SilentlyContinue that read as "already running" and the relaunch exited
# silently -- the stack ran with no guardian for an hour. An abandoned
# mutex means the previous owner is dead: take it.
$mutex = New-Object System.Threading.Mutex($false, "BarrysAIStackWatchdog")
$haveMutex = $false
try { $haveMutex = $mutex.WaitOne(0) }
catch [System.Threading.AbandonedMutexException] { $haveMutex = $true }
catch { $haveMutex = $false }
if (-not $haveMutex) { exit }

$LOG = "C:\Users\Owner\Desktop\AgentCompanyBackend\data\watchdog.log"
$OLLAMA = "C:\Users\Owner\AppData\Local\AMD\AI_Bundle\Ollama\ollama.exe"
$BACKEND_PY = "C:\Users\Owner\Desktop\AgentCompanyBackend\venv\Scripts\python.exe"
$BACKEND_DIR = "C:\Users\Owner\Desktop\AgentCompanyBackend\backend"
$DASH_PY = "C:\Users\Owner\AppData\Local\Programs\Python\Python312\python.exe"
$DASH_DIR = "C:\Users\Owner\Desktop\AgentDashboard"

function Log($msg) {
    try {
        if ((Get-Item $LOG -ErrorAction SilentlyContinue).Length -gt 1MB) {
            Get-Content $LOG -Tail 200 | Set-Content $LOG
        }
        "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg" | Add-Content $LOG
    } catch {}
}

# 2026-10-07 (Barry: "make the watchdog know when a video is being made ... make it know whats going on"):
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

function Alive($url) {
    # 2026-09-07: was TimeoutSec 3. A busy-but-healthy backend answers
    # /api/agents in well over 3s under load, so the old value reported a
    # working office as dead. 15s is longer than any healthy response and
    # still far shorter than the 45s loop.
    try {
        $r = Invoke-WebRequest -Uri $url -TimeoutSec 15 -UseBasicParsing
        return $r.StatusCode -eq 200
    } catch { return $false }
}

# A port with a listener means SOMETHING already owns this service.
# THIS IS THE GUARD THAT MATTERS. Windows lets a second process bind a port
# that is already bound, so "start another one" does NOT fail loudly -- it
# silently stacks a second full backend (its own update checker, watch loop,
# reflections, teamwork board) onto the same SQLite database. That is what
# happened on 2026-09-07: four backends and two dashboard servers were live
# at once, every loop running four times over, and the office slowed to the
# point that the health probe timed out -- which spawned yet another one.
# Never spawn into a port that already has an owner.
function PortBusy($port) {
    try {
        return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
    } catch { return $false }
}

function PortOwner($port) {
    try {
        return (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
                Select-Object -First 1 -ExpandProperty OwningProcess)
    } catch { return $null }
}

# Consecutive failed HTTP probes while the port IS held. Only after several
# in a row is the owner treated as genuinely hung and killed -- so a slow
# minute never costs a restart, but a real hang still gets fixed.
$backendStrikes = 0
$dashStrikes = 0
$STRIKES_BEFORE_KILL = 3
$STRIKES_WHILE_VIDEO = 20      # ~15 min of silence before a kill while a video is building/rendering
$lastKey = ""

Log "watchdog started (pid $PID)"

while ($true) {
    # Intentional-shutdown respect: when everything should stay OFF,
    # a pause flag stops all revivals until it is removed.
    # Flag file: data\watchdog_paused.flag
    if (Test-Path "C:\Users\Owner\Desktop\AgentCompanyBackend\data\watchdog_paused.flag") {
        Start-Sleep -Seconds 45
        continue
    }
    $acted = $false

    if (-not (PortBusy 11434) -and -not (Alive "http://127.0.0.1:11434/api/version")) {
        Log "Ollama DOWN -- restarting"
        Start-Process -FilePath $OLLAMA -ArgumentList "serve" -WindowStyle Hidden
        $acted = $true
    }

    if (-not (PortBusy 8420)) {
        Log "Backend DOWN (nothing listening on 8420) -- restarting"
        Start-Process -FilePath $BACKEND_PY -ArgumentList "main.py" -WorkingDirectory $BACKEND_DIR -WindowStyle Hidden
        $backendStrikes = 0
        $acted = $true
    }
    # 2026-10-07: /api/ping (loop liveness, no DB) -- /api/agents took 15s+ under a video turn and 3 slow answers
    # killed a working backend mid-turn (Barry: "whatever watchdog is doing, i need it fixed and optimized")
    else {
        $state = PingState "http://127.0.0.1:8420/api/ping"
        if ($null -eq $state) {
            $backendStrikes++
            # a build/render flag on disk, or the last thing seen was Ilnora at work (her writing turns carry no flag)
            $video = (VideoInProgress) -or ($lastKey -match 'Ilnora')
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
    }

    # --bind 127.0.0.1 is REQUIRED, not cosmetic. Barry's rule: private means
    # private. Without it python's http.server binds every interface and the
    # dashboard is reachable from anything on his network. The launcher was
    # fixed for this on 2026-09-07 and this respawn was not -- so the watchdog
    # kept putting the exposed copy back. Keep the flag.
    if (-not (PortBusy 8765)) {
        Log "Dashboard server DOWN (nothing listening on 8765) -- restarting"
        Start-Process -FilePath $DASH_PY -ArgumentList "C:\Users\Owner\Desktop\AgentCompanyBackend\scripts\dashboard_server.py","8765" -WorkingDirectory $DASH_DIR -WindowStyle Hidden   # 2026-10-17: same server, loopback in code, Cache-Control: no-store
        $dashStrikes = 0
        $acted = $true
    }
    elseif (-not (Alive "http://127.0.0.1:8765/index.html")) {
        $dashStrikes++
        Log "Dashboard held 8765 but did not answer ($dashStrikes/$STRIKES_BEFORE_KILL)"
        if ($dashStrikes -ge $STRIKES_BEFORE_KILL) {
            $owner = PortOwner 8765
            Log "Dashboard HUNG -- killing pid $owner and restarting"
            if ($owner) { Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue }
            Start-Sleep -Seconds 3
            Start-Process -FilePath $DASH_PY -ArgumentList "C:\Users\Owner\Desktop\AgentCompanyBackend\scripts\dashboard_server.py","8765" -WorkingDirectory $DASH_DIR -WindowStyle Hidden   # 2026-10-17: same server, loopback in code, Cache-Control: no-store
            $dashStrikes = 0
            $acted = $true
        }
    }
    else { $dashStrikes = 0 }

    # SEARXNG (2026-09-15) -- the office's local metasearch on 127.0.0.1:8080.
    # Port-guarded like everything else: never spawn into an owned port. The
    # start script does its own port check too, so a race cannot stack two.
    if (-not (PortBusy 8080)) {
        Log "SearXNG DOWN (nothing listening on 8080) -- restarting"
        Start-Process -FilePath "powershell.exe" -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File","C:\Users\Owner\Desktop\AgentCompanyBackend\scripts\start_searxng.ps1" -WindowStyle Hidden
        $acted = $true
    }

    # After any resurrection, give services time to boot before re-checking,
    # so a slow startup never triggers a duplicate instance.
    if ($acted) { Start-Sleep -Seconds 90 } else { Start-Sleep -Seconds 45 }
}
