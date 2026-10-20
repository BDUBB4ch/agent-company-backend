# Wait for the card to be free (no data/video_rendering.flag), then restart the backend the house way.
# Used 2026-10-17 04:40 when the HOME ONLY personality rule needed a restart before office hours but a render held
# the card. Polls every 30 s, gives up after -MaxMinutes (default 300). Prints what it did.
param([int]$MaxMinutes = 300)
$root = Split-Path -Parent $PSScriptRoot
$flag = Join-Path $root 'data\video_rendering.flag'
$deadline = (Get-Date).AddMinutes($MaxMinutes)
$mark = Join-Path $root 'data\reel_building.flag'   # 2026-10-18: a build holds this the whole way; the render flag has gaps between clips
while ((Test-Path $flag) -or (Test-Path $mark)) {
    if ((Get-Date) -gt $deadline) { Write-Host ("gave up at " + (Get-Date -Format HH:mm) + ": the flag never cleared"); exit 1 }
    Write-Host ("" + (Get-Date -Format HH:mm:ss) + " render still owns the card, waiting...")
    Start-Sleep -Seconds 30
}
Write-Host ("" + (Get-Date -Format HH:mm:ss) + " card free -- restarting")
& (Join-Path $PSScriptRoot 'restart_backend.ps1')
