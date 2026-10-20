# Start the office's local SearXNG (2026-09-15). Used by the watchdog and by
# hand. Native install (no Docker): tools\searxng (app, shallow git clone) +
# tools\searxng-venv (its own Python) + tools\searxng-office\settings.yml
# (the office's config, outside the app tree). Binds 127.0.0.1:8080 only.
#
# Manual:  powershell -ExecutionPolicy Bypass -File scripts\start_searxng.ps1
# Stop:    kill the python.exe whose command line contains "searx.webapp"
$ErrorActionPreference = "SilentlyContinue"
$ROOT = "C:\Users\Owner\Desktop\AgentCompanyBackend"
$PY   = "$ROOT\tools\searxng-venv\Scripts\python.exe"
$APP  = "$ROOT\tools\searxng"
$CFG  = "$ROOT\tools\searxng-office\settings.yml"
$LOG  = "$ROOT\data\searxng.log"

if (Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue) {
    Write-Output "searxng: port 8080 already has an owner -- not starting a second one"
    exit 0
}
$env:SEARXNG_SETTINGS_PATH = $CFG
$env:PYTHONIOENCODING = "utf-8"
# rotate the log past 2 MB
if ((Get-Item $LOG -ErrorAction SilentlyContinue).Length -gt 2MB) { Get-Content $LOG -Tail 400 | Set-Content $LOG }
Start-Process -FilePath $PY -ArgumentList "-m","searx.webapp" -WorkingDirectory $APP -WindowStyle Hidden `
    -RedirectStandardOutput "$LOG" -RedirectStandardError "$ROOT\data\searxng.err.log"
Write-Output "searxng: started (settings $CFG)"
