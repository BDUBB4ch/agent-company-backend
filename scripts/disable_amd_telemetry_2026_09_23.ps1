# Run as ADMINISTRATOR (right-click -> Run with PowerShell as admin).
# Disables AMD's "User Experience Program" data uploader (telemetry) and stops it now.
# Reversible: Set-Service AUEPLauncher -StartupType Automatic
$ErrorActionPreference = "Stop"
foreach ($svc in @("AUEPLauncher")) {
    if (Get-Service -Name $svc -ErrorAction SilentlyContinue) {
        Stop-Service -Name $svc -Force -ErrorAction SilentlyContinue
        Set-Service -Name $svc -StartupType Disabled
        Write-Host "$svc -> Disabled, stopped"
    }
}
# The AUEP master client under HKLM Run (StartAUEP) only feeds that service; leave it, the service is the uploader.
Get-Service AUEPLauncher | Select-Object Name, Status, StartType | Format-Table -AutoSize
Write-Host "Done. AMD Chat is a Radeon Software feature -- turn it off inside AMD Software: Adrenalin (AMD Chat tab / Settings), not here."
Read-Host "Press Enter to close"
