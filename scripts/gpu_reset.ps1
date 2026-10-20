# gpu_reset.ps1 -- clear the RX 9070 XT's driver state WITHOUT a reboot.
#
# Barry, 2026-09-04: "theres gotta be a way to clear the gpu without restarting
# my pc." There is. The slowdown this office has hit after render marathons
# (2026-08-29: 43s -> 267s/step on the same job) matches ROCm issue #6007 --
# "RDNA HIP memory pool fragmentation causes massive slowdown on Windows after a
# VRAM-heavy workload" -- and it PERSISTS after the process exits, which is why
# stop_server()/unload_all_models() do not clear it. A device-level driver
# restart does. Win+Ctrl+Shift+B does NOT: it resets the display stack only and
# leaves HIP state alone.
#
# What this does, in order:
#   1. stops everything holding a GPU context (ComfyUI on 8188/8189/8190, the
#      Bonsai llama-server, Ollama runners) -- a driver restart would kill them
#      mid-flight anyway, and a half-dead process is worse than a stopped one.
#   2. refuses to run if data/video_rendering.flag is up (a render is live).
#   3. pnputil /restart-device on the Radeon -- screen goes black ~2-5s.
#   4. reports the new driver state.
# NEEDS ADMIN. Right-click -> Run with PowerShell (as administrator), or from an
# elevated prompt:  powershell -ExecutionPolicy Bypass -File scripts\gpu_reset.ps1
# The watchdog brings Ollama/backend/dashboard back on its own within 45s.
# Untested against a real decayed state as of 2026-09-04 (the card was clean when
# it was written) -- the first genuine slowdown is the test. Measure s/step
# before and after; if it does not recover, THEN reboot.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$flag = Join-Path $root "data\video_rendering.flag"

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "NOT ELEVATED. pnputil /restart-device needs admin." -ForegroundColor Red
    Write-Host "Re-run from an elevated PowerShell, or right-click this file -> Run as administrator."
    exit 2
}
if (Test-Path $flag) {
    Write-Host "A render is live (data\video_rendering.flag = '$(Get-Content $flag)'). Refusing." -ForegroundColor Red
    exit 3
}

Write-Host "== 1. stopping GPU holders =="
$killed = @()
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*ComfyUI*main.py*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue; $killed += "ComfyUI pid $($_.ProcessId)" }
Get-Process llama-server -EA SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force; $killed += "llama-server pid $($_.Id)" }
# Ollama runners are llama-server.exe children of ollama.exe; the loop above got them.
if ($killed.Count) { $killed | ForEach-Object { "   stopped $_" } } else { "   nothing was holding the card" }
Start-Sleep -Seconds 3

Write-Host "== 2. locating the Radeon =="
$gpu = Get-PnpDevice -Class Display -EA SilentlyContinue |
       Where-Object { $_.FriendlyName -like '*Radeon*' -and $_.Status -eq 'OK' } |
       Select-Object -First 1
if (-not $gpu) { Write-Host "No Radeon display device found." -ForegroundColor Red; exit 4 }
"   $($gpu.FriendlyName)"
"   $($gpu.InstanceId)"

Write-Host "== 3. restarting the driver (screen will blink) =="
$t0 = Get-Date
& pnputil /restart-device "$($gpu.InstanceId)"
if ($LASTEXITCODE -ne 0) { Write-Host "pnputil exit $LASTEXITCODE" -ForegroundColor Red; exit 5 }
Start-Sleep -Seconds 4
$after = Get-PnpDevice -InstanceId $gpu.InstanceId
"   status after: $($after.Status)  ($([int]((Get-Date)-$t0).TotalSeconds)s)"

Write-Host "== done. watchdog revives Ollama/backend/dashboard within 45s =="
Write-Host "   verify: next render's s/step should be back to the clean-card number."
