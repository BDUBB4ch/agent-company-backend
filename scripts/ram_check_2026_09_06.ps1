Write-Output "=== WHEA / hardware error events (System log, all retained) ==="
Get-WinEvent -LogName System -MaxEvents 6000 -ErrorAction SilentlyContinue |
  Where-Object { $_.ProviderName -match 'WHEA|MemoryDiagnostic' } |
  Select-Object TimeCreated, ProviderName, Id, LevelDisplayName |
  Sort-Object TimeCreated -Descending | Format-Table -AutoSize

Write-Output ""
Write-Output "=== Bugcheck (1001) + unexpected shutdown (41) events ==="
Get-WinEvent -LogName System -MaxEvents 6000 -ErrorAction SilentlyContinue |
  Where-Object { $_.Id -in 1001,41 } |
  ForEach-Object {
    $first = ($_.Message -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -First 1)
    [pscustomobject]@{ Time=$_.TimeCreated; Id=$_.Id; Provider=$_.ProviderName; Msg=$first }
  } | Sort-Object Time -Descending | Select-Object -First 25 | Format-Table -AutoSize -Wrap

Write-Output ""
Write-Output "=== Oldest System log entry (how far back this evidence goes) ==="
Get-WinEvent -LogName System -MaxEvents 6000 -ErrorAction SilentlyContinue |
  Sort-Object TimeCreated | Select-Object -First 1 TimeCreated

Write-Output ""
Write-Output "=== Windows Memory Diagnostic results (has mdsched ever run?) ==="
$found = $false
foreach ($ln in @('Microsoft-Windows-MemoryDiagnostics-Results/Debug','System')) {
  $e = Get-WinEvent -FilterHashtable @{LogName=$ln; ProviderName='Microsoft-Windows-MemoryDiagnostics-Results'} -MaxEvents 10 -ErrorAction SilentlyContinue
  if ($e) { $found = $true; $e | Select-Object TimeCreated,Id,Message | Format-List }
}
if (-not $found) { Write-Output "NONE - Windows Memory Diagnostic has never reported a result on this machine." }

Write-Output ""
Write-Output "=== Memory config / spec ==="
Get-CimInstance Win32_PhysicalMemory | Select-Object DeviceLocator,PartNumber,SerialNumber,
  @{n='GB';e={$_.Capacity/1GB}},Speed,ConfiguredClockSpeed,ConfiguredVoltage,DataWidth,TotalWidth |
  Format-Table -AutoSize

Write-Output ""
Write-Output "=== BIOS / board ==="
Get-CimInstance Win32_BIOS | Select-Object Manufacturer,SMBIOSBIOSVersion,ReleaseDate | Format-List
Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer,Product,Version | Format-List
