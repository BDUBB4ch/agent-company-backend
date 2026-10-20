$targets = @('C:\Users\Owner\Desktop\Archive\sd safe tensor','C:\Users\Owner\Desktop\Archive\GODOT')
foreach ($t in $targets) {
  "==================================================================="
  "=== $t"
  if (-not (Test-Path $t)) { "  NOT FOUND"; continue }
  $files = Get-ChildItem $t -Recurse -File -Force -ErrorAction SilentlyContinue
  "  Total: {0:N2} GB across {1} files" -f (($files | Measure-Object Length -Sum).Sum/1GB), $files.Count
  "  Newest file: {0}" -f ($files | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -Expand LastWriteTime)
  ""
  "  --- Subfolders ---"
  Get-ChildItem $t -Directory -Force -ErrorAction SilentlyContinue | ForEach-Object {
    $sz = (Get-ChildItem $_.FullName -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
    [pscustomobject]@{ Folder=$_.Name; GB=[math]::Round($sz/1GB,2) }
  } | Sort-Object GB -Descending | Select-Object -First 15 | Format-Table -AutoSize
  ""
  "  --- 25 largest files ---"
  $files | Sort-Object Length -Descending | Select-Object -First 25 `
    @{n='GB';e={[math]::Round($_.Length/1GB,2)}}, Name, LastWriteTime | Format-Table -AutoSize
  ""
}
