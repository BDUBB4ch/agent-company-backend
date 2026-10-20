$os = Get-CimInstance Win32_OperatingSystem
"RAM total       : {0:N1} GB" -f ($os.TotalVisibleMemorySize/1MB)
"RAM free now    : {0:N1} GB" -f ($os.FreePhysicalMemory/1MB)
"Commit limit    : {0:N1} GB" -f ($os.TotalVirtualMemorySize/1MB)
"Commit in use   : {0:N1} GB" -f (($os.TotalVirtualMemorySize - $os.FreeVirtualMemory)/1MB)
""
"--- Pagefile (PeakUsage = high-water mark since boot) ---"
Get-CimInstance Win32_PageFileUsage | Select-Object Name,
  @{n='AllocGB';e={[math]::Round($_.AllocatedBaseSize/1KB,1)}},
  @{n='CurrentGB';e={[math]::Round($_.CurrentUsage/1KB,1)}},
  @{n='PeakGB';e={[math]::Round($_.PeakUsage/1KB,1)}} | Format-Table -AutoSize
""
"--- Uptime ---"
"Booted: {0}" -f $os.LastBootUpTime
""
"--- Top 10 memory consumers right now ---"
Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 10 Name,
  @{n='WS_GB';e={[math]::Round($_.WorkingSet64/1GB,2)}} | Format-Table -AutoSize
