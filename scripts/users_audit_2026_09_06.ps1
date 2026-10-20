function Show-Dirs($path, $label, $top) {
  "=== $label ==="
  Get-ChildItem $path -Directory -Force -ErrorAction SilentlyContinue | ForEach-Object {
    $sz = (Get-ChildItem $_.FullName -Recurse -File -Force -ErrorAction SilentlyContinue |
           Measure-Object Length -Sum).Sum
    [pscustomobject]@{ Folder=$_.Name; GB=[math]::Round($sz/1GB,2) }
  } | Sort-Object GB -Descending | Select-Object -First $top | Format-Table -AutoSize
  ""
}
Show-Dirs 'C:\Users\Owner' 'C:\Users\Owner' 10
Show-Dirs 'C:\Users\Owner\Desktop' 'Desktop' 10
Show-Dirs 'C:\Users\Owner\Desktop\AgentCompanyBackend\tools\ComfyUI\models' 'ComfyUI models' 12

"=== Recycle Bin per drive ==="
foreach ($d in 'C','D') {
  $p = "${d}:\`$Recycle.Bin"
  $sz = (Get-ChildItem $p -Recurse -File -Force -ErrorAction SilentlyContinue |
         Measure-Object Length -Sum).Sum
  "{0}: {1,8:N2} GB" -f $d, ($sz/1GB)
}
""
"=== hiberfil / pagefile via WMI (permission-safe) ==="
Get-CimInstance Win32_PageFileUsage | Select-Object Name,
  @{n='AllocGB';e={[math]::Round($_.AllocatedBaseSize/1KB,1)}} | Format-Table -AutoSize
"Fast Startup (HiberbootEnabled): " + (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power' -Name HiberbootEnabled -ErrorAction SilentlyContinue).HiberbootEnabled
