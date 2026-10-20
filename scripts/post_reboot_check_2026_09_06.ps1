$os = Get-CimInstance Win32_OperatingSystem
"Booted          : {0}" -f $os.LastBootUpTime
"Uptime          : {0:N0} min" -f ((Get-Date) - $os.LastBootUpTime).TotalMinutes
""
"RAM total       : {0:N1} GB" -f ($os.TotalVisibleMemorySize/1MB)
"RAM free        : {0:N1} GB" -f ($os.FreePhysicalMemory/1MB)
"Commit limit    : {0:N1} GB" -f ($os.TotalVirtualMemorySize/1MB)
"Commit in use   : {0:N1} GB" -f (($os.TotalVirtualMemorySize - $os.FreeVirtualMemory)/1MB)
""
"--- Pagefile config (this is the thing to verify) ---"
$pf = Get-CimInstance Win32_PageFileUsage
if (-not $pf) { "NO PAGEFILE FOUND" }
$pf | Select-Object Name,
  @{n='AllocGB';e={[math]::Round($_.AllocatedBaseSize/1KB,1)}},
  @{n='CurrentGB';e={[math]::Round($_.CurrentUsage/1KB,1)}},
  @{n='PeakGB';e={[math]::Round($_.PeakUsage/1KB,1)}} | Format-Table -AutoSize
""
"--- Memory Compression (the number that decides the RAM buy) ---"
$mc = Get-Process 'Memory Compression' -ErrorAction SilentlyContinue
if ($mc) { "Memory Compression: {0:N2} GB" -f ($mc.WorkingSet64/1GB) } else { "Memory Compression: not running / 0" }
""
"--- Top 8 consumers ---"
Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 8 Name,
  @{n='WS_GB';e={[math]::Round($_.WorkingSet64/1GB,2)}} | Format-Table -AutoSize
""
"--- Disk free ---"
Get-Volume -DriveLetter C,D | Select-Object DriveLetter,
  @{n='FreeGB';e={[math]::Round($_.SizeRemaining/1GB,1)}} | Format-Table -AutoSize
""
"--- Stack up? ---"
foreach ($p in 8420,11434,8765) {
  $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
  "port {0,-6}: {1}" -f $p, $(if($c){'LISTENING'}else{'down'})
}
