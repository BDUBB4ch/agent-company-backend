# Windows fluff removal (2026-10-09, Barry: "check windows for fluff and get rid of it").
# Removes: Bing Wallpaper/Search/News/Weather, Copilot (store + win32), McAfee Security Scan Plus + WebAdvisor.
# Disables at startup (apps stay installed): Teams, Canva availability agent, Epson monitors x2, Adobe Acrobat
# Synchronizer, AMD User Experience Program (telemetry), Bing Wallpaper daemon, McAfee scan scheduler.
# Left alone on purpose: OneDrive (already off at startup), Steam, Docker Desktop, Realtek audio, Security Health,
# AMD Noise Suppression (mic feature -- Barry's call).
$ErrorActionPreference = 'Continue'
$log = @()
function Note($m) { $script:log += $m; Write-Output $m }

# 1. Store apps
foreach ($n in 'Microsoft.BingWallpaper','Microsoft.BingSearch','Microsoft.BingNews','Microsoft.BingWeather','Microsoft.Copilot') {
    $p = Get-AppxPackage -Name $n -ErrorAction SilentlyContinue
    if ($p) { try { $p | Remove-AppxPackage -ErrorAction Stop; Note "removed store app: $n" } catch { Note "FAILED store app $n : $($_.Exception.Message)" } }
    else { Note "store app not present: $n" }
}

# 2. Win32 uninstallers (silent where the installer supports it)
$u = @(
  @{ name='McAfee Security Scan Plus'; exe='C:\Program Files (x86)\McAfee Security Scan\uninstall.exe'; args='/s' },
  @{ name='WebAdvisor by McAfee';      exe='C:\Program Files\McAfee\WebAdvisor\Uninstaller.exe';          args='/S' },
  @{ name='Copilot (win32)';           exe='C:\Program Files (x86)\Microsoft\Copilot\Application\155.0.4283.45\Installer\copilot_setup.exe'; args='--uninstall --mscopilot --channel=stable --system-level --force-uninstall' }
)
foreach ($x in $u) {
    if (Test-Path $x.exe) {
        try { $p = Start-Process -FilePath $x.exe -ArgumentList $x.args -Wait -PassThru -ErrorAction Stop; Note "uninstaller $($x.name): exit $($p.ExitCode)" }
        catch { Note "FAILED uninstaller $($x.name): $($_.Exception.Message)" }
    } else { Note "uninstaller not found (already gone?): $($x.name)" }
}

# 3. Startup entries: delete the junk ones, disable the rest via StartupApproved (what Task Manager writes)
$disabled = [byte[]](3,0,0,0,0,0,0,0,0,0,0,0)
$runKeys = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run','HKLM:\Software\Microsoft\Windows\CurrentVersion\Run','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run'
$delete  = 'BingWallpaperDaemon','McAfee Security Scan Plus','MicrosoftCopilotAutoLaunch*'
$disable = 'Teams','CanvaAutoLaunchAvailabilityCheckAgent','EPSDNMON','EPPCCMON','Adobe Acrobat Synchronizer','StartAUEP'
foreach ($k in $runKeys) {
    if (-not (Test-Path $k)) { continue }
    $props = (Get-ItemProperty $k).PSObject.Properties | Where-Object { $_.Name -notlike 'PS*' }
    foreach ($p in $props) {
        foreach ($d in $delete) { if ($p.Name -like $d) { Remove-ItemProperty -Path $k -Name $p.Name -ErrorAction SilentlyContinue; Note "deleted startup entry: $($p.Name) ($k)" } }
        foreach ($d in $disable) {
            if ($p.Name -eq $d) {
                $ap = if ($k -like 'HKCU*') { 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run' }
                      elseif ($k -like '*WOW6432Node*') { 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run32' }
                      else { 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run' }
                try { if (-not (Test-Path $ap)) { New-Item -Path $ap -Force | Out-Null }; Set-ItemProperty -Path $ap -Name $p.Name -Value $disabled -Type Binary -ErrorAction Stop; Note "disabled at startup: $($p.Name) ($k)" }
                catch { Note "FAILED to disable $($p.Name): $($_.Exception.Message)" }
            }
        }
    }
}
# Startup-folder items
foreach ($f in (Get-ChildItem "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup" -ErrorAction SilentlyContinue)) {
    Note "startup folder item left as is: $($f.Name)"
}

# 4. Kill what's running from the removed/disabled set right now
foreach ($pn in 'BingWallpaper','UnInstDaemon','McUICnt','SSScheduler','PhoneExperienceHost','msteams','ms-teams','AUEPMaster','AUEPUF','EPSDNMON','EPPCCMON','AdobeCollabSync') {
    $r = Get-Process -Name $pn -ErrorAction SilentlyContinue
    if ($r) { $r | Stop-Process -Force -ErrorAction SilentlyContinue; Note "stopped running: $pn" }
}
"`n== SUMMARY =="
$log
