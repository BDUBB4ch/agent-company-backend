# 2026-10-18: wait for the Henbane rebuild to release the card, preflight, restart the backend (new video_folder code),
# then fold the flat Henbane MP4 into its own folder. Log: data/after_card_free_2026_10_18.log
$root = Split-Path -Parent $PSScriptRoot
$log = Join-Path $root 'data\after_card_free_2026_10_18.log'
function Say($m) { ("" + (Get-Date -Format 'HH:mm:ss') + " " + $m) | Tee-Object -FilePath $log -Append }
$flag = Join-Path $root 'data\video_rendering.flag'
$deadline = (Get-Date).AddHours(6)
$mark = Join-Path $root 'data\reel_building.flag'   # the build's own mark -- the render flag has gaps between clips (14:26 lesson)
while ((Test-Path $flag) -or (Test-Path $mark)) { if ((Get-Date) -gt $deadline) { Say 'gave up: flag never cleared'; exit 1 }; Start-Sleep -Seconds 60 }
Say 'card free'
& (Join-Path $root 'venv\Scripts\python.exe') (Join-Path $root 'scripts\preflight_check.py') | Out-Null
if ($LASTEXITCODE -ne 0) { Say 'preflight FAILED -- no restart'; exit 1 }
& (Join-Path $PSScriptRoot 'restart_backend.ps1') | ForEach-Object { Say $_ }
if ($LASTEXITCODE -ne 0) { Say 'restart did not come back'; exit 1 }
& (Join-Path $root 'venv\Scripts\python.exe') -X utf8 (Join-Path $root 'scripts\backfill_video_folders_2026_10_18.py') --apply 2>&1 | ForEach-Object { Say $_ }
Say 'done'
