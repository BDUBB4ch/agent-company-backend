"=== C: space ==="
Get-Volume -DriveLetter C | Select-Object @{n='SizeGB';e={[math]::Round($_.Size/1GB,1)}},
  @{n='FreeGB';e={[math]::Round($_.SizeRemaining/1GB,1)}},
  @{n='UsedGB';e={[math]::Round(($_.Size-$_.SizeRemaining)/1GB,1)}} | Format-Table -AutoSize

"=== System files at C:\ root ==="
foreach ($f in 'C:\hiberfil.sys','C:\pagefile.sys','C:\swapfile.sys') {
  $i = Get-Item $f -Force -ErrorAction SilentlyContinue
  if ($i) { "{0,-18} {1,8:N1} GB" -f $i.Name, ($i.Length/1GB) }
  else    { "{0,-18} not present" -f (Split-Path $f -Leaf) }
}
""
"=== Hibernation status (powercfg /a) ==="
powercfg /a
""
"=== Shadow copy / System Restore usage ==="
vssadmin list shadowstorage 2>&1 | Select-String -Pattern 'volume|Used|Allocated|Maximum'
""
"=== Top-level folders on C: (GB) ==="
Get-ChildItem C:\ -Directory -Force -ErrorAction SilentlyContinue | ForEach-Object {
  $sz = (Get-ChildItem $_.FullName -Recurse -File -Force -ErrorAction SilentlyContinue |
         Measure-Object Length -Sum).Sum
  [pscustomobject]@{ Folder=$_.Name; GB=[math]::Round($sz/1GB,2) }
} | Sort-Object GB -Descending | Select-Object -First 12 | Format-Table -AutoSize
