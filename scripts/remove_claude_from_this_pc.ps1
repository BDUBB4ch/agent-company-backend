# REMOVE EVERYTHING CLAUDE / ANTHROPIC FROM THIS PC
# Barry, 2026-09-06: "if any of it links to anthropic, it goes."
#
# YOU run this (right-click -> Run with PowerShell, or from an elevated
# PowerShell). It deletes ~11.3 GB of Claude data and uninstalls the app.
# Nothing here touches the agent build: the office lives in
# Desktop\AgentCompanyBackend and Desktop\AgentDashboard, and its record is
# now in AgentCompanyBackend\BARRYS-AGENTS.md + docs\agents-memory\.
#
# What it removes (measured 2026-09-06):
#   Claude desktop app (winget Anthropic.Claude, Store package)
#   C:\Users\Owner\.local\bin\claude.exe               (Claude Code CLI)
#   C:\Users\Owner\AppData\Roaming\Claude               (10.4 GB app data, MCP config, VM bundles)
#   C:\Users\Owner\.claude                              (844 MB: transcripts, skills, settings, login token, memory)
#   C:\Users\Owner\.claude.json  and  .claude.json.backup
#   C:\Users\Owner\AppData\Local\claude                 (CLI cache)
#   C:\Users\Owner\AppData\Local\Temp\claude
#   Desktop\AgentCompanyBackend\.claude                 (project settings for the CLI)
#   Desktop\AgentCompanyBackend\CLAUDE.md               (merged into BARRYS-AGENTS.md first)
# The Chrome extension (Claude in Chrome) must be removed from chrome://extensions
# by hand -- deleting its folder does not uninstall it.
#
# Close the Claude app BEFORE running this (the app data is locked while it runs).

$ErrorActionPreference = "Continue"
$backend = "C:\Users\Owner\Desktop\AgentCompanyBackend"

if (-not (Test-Path "$backend\BARRYS-AGENTS.md")) {
    Write-Host "STOP: $backend\BARRYS-AGENTS.md is missing -- the build record has not been preserved. Not deleting anything." -ForegroundColor Red
    exit 1
}

Write-Host "Closing Claude..."
Get-Process claude -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3

Write-Host "Uninstalling the Claude desktop app..."
winget uninstall --id Anthropic.Claude --silent --disable-interactivity 2>&1 | Out-Host
Get-AppxPackage -Name "*Claude*" -ErrorAction SilentlyContinue | Remove-AppxPackage -ErrorAction SilentlyContinue

$targets = @(
    "$env:USERPROFILE\.local\bin\claude.exe",
    "$env:APPDATA\Claude",
    "$env:USERPROFILE\.claude",
    "$env:USERPROFILE\.claude.json",
    "$env:USERPROFILE\.claude.json.backup",
    "$env:LOCALAPPDATA\claude",
    "$env:LOCALAPPDATA\Temp\claude",
    "$backend\.claude",
    "$backend\CLAUDE.md"
)
foreach ($t in $targets) {
    if (Test-Path $t) {
        Write-Host "removing $t"
        Remove-Item -LiteralPath $t -Recurse -Force -ErrorAction Continue
    }
}

Write-Host ""
Write-Host "Left for you by hand:" -ForegroundColor Yellow
Write-Host "  1. Chrome -> chrome://extensions -> remove 'Claude'."
Write-Host "  2. Any Claude entries in Start Menu / taskbar pins."
Write-Host ""
$left = $targets | Where-Object { Test-Path $_ }
if ($left) { Write-Host "Still present (locked or permission):" -ForegroundColor Red; $left | ForEach-Object { "  $_" } }
else { Write-Host "Done. Nothing Claude remains in the paths above. The office is untouched." -ForegroundColor Green }
