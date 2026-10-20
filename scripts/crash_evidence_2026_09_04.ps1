# Read-only: what killed the machine at 06:29 on 2026-09-04 (Kernel-Power 41).
# WHEA = hardware error (CPU/PCIe/GPU); BugCheck 1001 = a real BSOD with a dump;
# amdkmdag / Display 4101 = GPU driver timeout/reset; nothing at all = power loss
# or a hang so hard nothing could write.
$since = (Get-Date).AddHours(-30)
Write-Host "--- WHEA / BugCheck / Display / AMD events:"
Get-WinEvent -FilterHashtable @{LogName = 'System'; StartTime = $since } -ErrorAction SilentlyContinue |
    Where-Object { $_.ProviderName -match 'WHEA|BugCheck|Display|amdkmdag|amdkmdap|Kernel-Power|Kernel-Boot' -and $_.Id -ne 12 } |
    Sort-Object TimeCreated |
    ForEach-Object {
        $first = ($_.Message -split "`n")[0]
        if ($first.Length -gt 110) { $first = $first.Substring(0, 110) }
        '{0}  id={1,-5} {2,-34} {3}' -f $_.TimeCreated.ToString('MM-dd HH:mm:ss'), $_.Id, $_.ProviderName, $first
    }
Write-Host "--- Kernel-Power 41 details (BugcheckCode / PowerButtonTimestamp):"
Get-WinEvent -FilterHashtable @{LogName = 'System'; ProviderName = 'Microsoft-Windows-Kernel-Power'; Id = 41; StartTime = $since } -ErrorAction SilentlyContinue |
    ForEach-Object { ([xml]$_.ToXml()).Event.EventData.Data | ForEach-Object { '  {0} = {1}' -f $_.Name, $_.'#text' } }
Write-Host "--- minidumps:"
Get-ChildItem C:\Windows\Minidump -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 3 | ForEach-Object { '  ' + $_.LastWriteTime.ToString('MM-dd HH:mm') + '  ' + $_.Name }
Write-Host "--- MEMORY.DMP:"
Get-Item C:\Windows\MEMORY.DMP -ErrorAction SilentlyContinue | ForEach-Object { '  ' + $_.LastWriteTime.ToString('MM-dd HH:mm') + '  ' + [math]::Round($_.Length / 1MB) + ' MB' }
Write-Host "--- last log lines the machine wrote before the crash (Application+System, 06:15-06:29):"
Get-WinEvent -FilterHashtable @{LogName = 'System', 'Application'; StartTime = (Get-Date '2026-09-04 06:15'); EndTime = (Get-Date '2026-09-04 06:29:10') } -ErrorAction SilentlyContinue |
    Sort-Object TimeCreated | Select-Object -Last 8 |
    ForEach-Object { '{0}  {1}  id={2}' -f $_.TimeCreated.ToString('HH:mm:ss'), $_.ProviderName, $_.Id }
