# Elevated half of the fluff removal (2026-10-10, Barry: "run the admin ones"). Runs under UAC once.
$log = 'C:\Users\Owner\Desktop\AgentCompanyBackend\data\defluff_admin_2026_10_10.log'
function Note($m) { "$(Get-Date -Format 'HH:mm:ss') $m" | Add-Content $log; Write-Output $m }
"== admin defluff $(Get-Date) ==" | Set-Content $log

# 1. WebAdvisor by McAfee
$wa = 'C:\Program Files\McAfee\WebAdvisor\Uninstaller.exe'
if (Test-Path $wa) {
    foreach ($a in @('/S', '/s', '/quiet')) {
        try { $p = Start-Process -FilePath $wa -ArgumentList $a -Wait -PassThru -ErrorAction Stop; Note "WebAdvisor uninstaller $a -> exit $($p.ExitCode)"; if ($p.ExitCode -eq 0 -or -not (Test-Path $wa)) { break } }
        catch { Note "WebAdvisor $a failed: $($_.Exception.Message)" }
    }
} else { Note "WebAdvisor: uninstaller not found (already gone)" }

# 2. Copilot (win32, system-level)
$cp = Get-ChildItem 'C:\Program Files (x86)\Microsoft\Copilot\Application\*\Installer\copilot_setup.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($cp) {
    try { $p = Start-Process -FilePath $cp.FullName -ArgumentList '--uninstall --mscopilot --channel=stable --system-level --force-uninstall' -Wait -PassThru -ErrorAction Stop; Note "Copilot win32 uninstaller -> exit $($p.ExitCode)" }
    catch { Note "Copilot uninstaller failed: $($_.Exception.Message)" }
} else { Note "Copilot win32: installer not found (already gone)" }

# 3. Machine-wide startup entries: disable (Task Manager style), apps stay
$disabled = [byte[]](3,0,0,0,0,0,0,0,0,0,0,0)
$ap = 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run'
if (-not (Test-Path $ap)) { New-Item -Path $ap -Force | Out-Null }
foreach ($n in 'EPPCCMON', 'StartAUEP') {
    try { Set-ItemProperty -Path $ap -Name $n -Value $disabled -Type Binary -ErrorAction Stop; Note "disabled at startup (HKLM): $n" }
    catch { Note "FAILED to disable $n : $($_.Exception.Message)" }
}

# 4. What is left registered
$left = (Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*', 'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*', 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -match 'McAfee|Copilot|Bing' }).DisplayName
Note ("still registered: " + ($(if ($left) { $left -join ', ' } else { 'none' })))
Note "done"
