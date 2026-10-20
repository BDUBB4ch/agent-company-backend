# ltx25_scheduled_test.ps1 -- run one LTX-2.5 office-workflow test on the D: rig
# in a way that SURVIVES the Claude session dying.
#
# Why this exists (2026-09-04): the `--reserve-vram 1.5 --cache-none` test was
# launched as a child of a Claude background task; a usage-limit interruption
# killed the session, and the rig and the poller died with it mid-render -- clean
# log ending at 05:16:49, no error, no OOM, no Windows event. The record already
# says it: processes started from a Claude session die with that session; anything
# that must outlive it belongs to Task Scheduler. So: register this with schtasks
# and RUN it; it owns the render flag with its own token, starts the rig with the
# exact flags under test, submits, polls to completion, verifies the clip, and
# clears only its own flag.
#
# Usage (from schtasks or a plain shell):
#   powershell -ExecutionPolicy Bypass -File scripts\ltx25_scheduled_test.ps1 `
#       -Label r15_cachenone -ReserveVram 1.5 -CacheNone -W 1024 -H 576 -Sec 5 -Fps 24
# Results: data\ltx25_sched_<Label>.log  (bench) and D:\ComfyUI25\ltx25_sched_<Label>.log (server)

param(
    [string]$Label = "sched",
    [double]$ReserveVram = 1.5,
    [switch]$CacheNone,
    [switch]$NoFlagEnv,          # set to test WITHOUT PYTORCH_NO_HIP_MEMORY_CACHING
    [int]$W = 1024, [int]$H = 576, [int]$Sec = 5, [int]$Fps = 24
)
$ErrorActionPreference = "Continue"
$root  = "C:\Users\Owner\Desktop\AgentCompanyBackend"
$rig   = "D:\ComfyUI25"
$flag  = "$root\data\video_rendering.flag"
$bench = "$root\data\ltx25_sched_$Label.log"
$slog  = "$rig\ltx25_sched_$Label.log"
$py    = "$rig\venv\Scripts\python.exe"
$opy   = "$root\venv\Scripts\python.exe"
$tok   = "ltx25-sched-$Label-$(Get-Date -Format HHmmss)"

function Log($m) { $line = "$(Get-Date -Format 'HH:mm:ss') $m"; Add-Content $bench $line; Write-Host $line }
Set-Content $bench "=== ltx25 scheduled test '$Label' start $(Get-Date) ===`nreserve=$ReserveVram cache-none=$($CacheNone.IsPresent) flag-env=$(-not $NoFlagEnv.IsPresent) size=${W}x${H} ${Sec}s@${Fps}"

# refuse to trample someone else's render
if (Test-Path $flag) { $t = Get-Content $flag; if ($t -notlike "ltx25-*") { Log "another render owns the flag ($t) -- refusing"; exit 3 } }
Set-Content $flag $tok
Log "flag raised ($tok)"

# stop anything already on the rig / holding the card the way the office does
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*ComfyUI25*main.py*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue; Log "stopped old rig pid $($_.ProcessId)" }
Get-Process llama-server -EA SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force; Log "stopped llama-server $($_.Id) (GPU)" }
Start-Sleep 4

# launch the rig with EXACTLY the flags under test
$args = @("$rig\main.py", "--port", "8190", "--use-pytorch-cross-attention", "--reserve-vram", "$ReserveVram")
if ($CacheNone) { $args += "--cache-none" }
$env:PYTORCH_NO_HIP_MEMORY_CACHING = $(if ($NoFlagEnv) { $null } else { "1" })
if ($NoFlagEnv) { Remove-Item Env:PYTORCH_NO_HIP_MEMORY_CACHING -EA SilentlyContinue }
$proc = Start-Process -FilePath $py -ArgumentList $args -WorkingDirectory $rig -RedirectStandardOutput $slog -RedirectStandardError "$slog.err" -PassThru -WindowStyle Hidden
Log "rig launched pid $($proc.Id): $($args -join ' ')  env-flag=$(-not $NoFlagEnv.IsPresent)"

# wait for it
$up = $false
for ($i = 0; $i -lt 30; $i++) { Start-Sleep 10; try { Invoke-WebRequest "http://127.0.0.1:8190/queue" -UseBasicParsing -TimeoutSec 5 | Out-Null; $up = $true; break } catch {} }
if (-not $up) { Log "rig never came up -- see $slog / $slog.err"; Remove-Item $flag -EA SilentlyContinue; exit 4 }
Log "rig up"

# submit through the SAME script the earlier tests used (same substitutions as the office)
$t0 = Get-Date
& $opy "$root\scripts\test_ltx25_office_workflow_2026_09_04.py" $Sec $W $H $Fps 2>&1 | ForEach-Object { if ($_ -notmatch "elapsed") { Log "bench: $_" } }
$mins = [math]::Round(((Get-Date) - $t0).TotalMinutes, 1)
Log "bench finished in $mins min"

# per-stage numbers straight from the server log
$s1 = (Select-String -Path $slog -Pattern '8/8 \[[0-9:]+<[0-9:?]+, *[0-9.]+s/it\]' -AllMatches | ForEach-Object { $_.Matches.Value } | Select-Object -Last 1)
$s2 = (Select-String -Path $slog -Pattern '3/3 \[[0-9:]+<[0-9:?]+, *[0-9.]+s/it\]' -AllMatches | ForEach-Object { $_.Matches.Value } | Select-Object -Last 1)
$oom = (Select-String -Path $slog -Pattern 'out of memory' | Measure-Object).Count
Log "stage1: $s1"
Log "stage2: $s2"
Log "OOM lines: $oom"

# verify the newest clip: duration, level, transcript
$newest = Get-ChildItem "$rig\output\video\agent_*.mp4" -EA SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
if ($newest -and $newest.LastWriteTime -gt $t0) {
    Push-Location "$root\backend"
    $v = & $opy -c "import sys; sys.path.insert(0,'.'); import media_understanding as mu; p=r'$($newest.FullName)'; d=mu.probe_media(p); t=mu.transcribe_audio(p).get('text'); print('%.2fs mean %.1f dBFS peak %.1f transcript=%r' % (d['duration_s'],d['mean_dbfs'],d['peak_dbfs'],t))" 2>&1 | Select-Object -Last 1
    Pop-Location
    Log "clip $($newest.Name): $v"
} else { Log "no new clip produced" }

# tidy: stop the rig so the office gets the card back, clear ONLY our flag
Stop-Process -Id $proc.Id -Force -EA SilentlyContinue
if ((Test-Path $flag) -and ((Get-Content $flag) -eq $tok)) { Remove-Item $flag; Log "flag cleared" }
Log "=== done ==="
