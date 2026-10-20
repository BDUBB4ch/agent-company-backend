# Restart the office backend the house way (CLAUDE.md): kill the PORT OWNER of 8420 and let the watchdog revive it.
# Refuses while a render runs (data/video_rendering.flag). Run preflight_check.py first.
$root = Split-Path -Parent $PSScriptRoot
if (Test-Path (Join-Path $root 'data\video_rendering.flag')) { Write-Host 'REFUSED: a render owns the card (data/video_rendering.flag)'; exit 2 }
# 2026-10-18 14:26: video_rendering.flag is PER RENDER and absent for a moment between a build's clips -- a waiter saw that
# gap and this script killed Henbane's build 2 h 20 min in. A build holds data/reel_building.flag the whole way through.
if (Test-Path (Join-Path $root 'data\reel_building.flag')) { Write-Host 'REFUSED: a video is building (data/reel_building.flag)'; exit 2 }
$conn = Get-NetTCPConnection -LocalPort 8420 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) { Stop-Process -Id $conn.OwningProcess -Force; Write-Host ("killed backend pid " + $conn.OwningProcess) } else { Write-Host 'no listener on 8420' }
for ($i = 1; $i -le 30; $i++) {
    Start-Sleep -Seconds 5
    try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8420/api/ping' -TimeoutSec 3; Write-Host ("back after ~" + ($i * 5) + "s: busy=" + $r.busy); exit 0 } catch {}
}
Write-Host 'NOT BACK after 150 s -- check data/watchdog.log'; exit 1
