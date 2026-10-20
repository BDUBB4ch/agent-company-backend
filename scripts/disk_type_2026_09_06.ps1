"=== Physical disks ==="
Get-PhysicalDisk | Select-Object DeviceId, FriendlyName, MediaType, BusType,
  @{n='SizeGB';e={[math]::Round($_.Size/1GB,0)}}, HealthStatus | Format-Table -AutoSize
""
"=== Volumes / drive letters ==="
Get-Volume | Where-Object { $_.DriveLetter } | Select-Object DriveLetter, FileSystemLabel,
  @{n='SizeGB';e={[math]::Round($_.Size/1GB,0)}},
  @{n='FreeGB';e={[math]::Round($_.SizeRemaining/1GB,1)}}, HealthStatus | Format-Table -AutoSize
""
"=== Which disk backs each partition ==="
Get-Partition | Where-Object { $_.DriveLetter } |
  Select-Object DriveLetter, DiskNumber, @{n='SizeGB';e={[math]::Round($_.Size/1GB,0)}} | Format-Table -AutoSize
