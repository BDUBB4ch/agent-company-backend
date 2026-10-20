$ErrorActionPreference = 'Continue'
$log = 'C:\Users\Owner\Desktop\AgentCompanyBackend\data\archive_move_2026-09-06.log'
function L($m) { $line = "[{0}] {1}" -f (Get-Date -f 'HH:mm:ss'), $m; $line; Add-Content $log $line }

L "=== Archive move started ==="
$dFree = (Get-Volume -DriveLetter D).SizeRemaining/1GB
L ("D: free before: {0:N1} GB" -f $dFree)
if ($dFree -lt 250) { L "ABORT: not enough room on D:"; exit 1 }

New-Item -ItemType Directory -Path 'D:\Archive' -Force | Out-Null

$jobs = @(
  @{ Src='C:\Users\Owner\Desktop\Archive\GODOT';         Dst='D:\Archive\GODOT' },
  @{ Src='C:\Users\Owner\Desktop\Archive\sd safe tensor'; Dst='D:\Archive\sd safe tensor' }
)

foreach ($j in $jobs) {
  $src = $j.Src; $dst = $j.Dst
  L ""
  L "--- COPY: $src  ->  $dst"
  if (-not (Test-Path $src)) { L "  source missing, skipping"; continue }

  $sf = Get-ChildItem $src -Recurse -File -Force -ErrorAction SilentlyContinue
  $sCount = $sf.Count; $sBytes = ($sf | Measure-Object Length -Sum).Sum
  L ("  source: {0} files, {1:N0} bytes ({2:N2} GB)" -f $sCount, $sBytes, ($sBytes/1GB))

  # copy only -- source is NOT touched until verification passes
  robocopy $src $dst /E /R:1 /W:1 /NFL /NDL /NP /NJH /NJS | Out-Null
  $rc = $LASTEXITCODE
  L "  robocopy exit code: $rc  (0-7 = ok, 8+ = error)"
  if ($rc -ge 8) { L "  COPY FAILED -- source left untouched"; continue }

  $df = Get-ChildItem $dst -Recurse -File -Force -ErrorAction SilentlyContinue
  $dCount = $df.Count; $dBytes = ($df | Measure-Object Length -Sum).Sum
  L ("  dest  : {0} files, {1:N0} bytes ({2:N2} GB)" -f $dCount, $dBytes, ($dBytes/1GB))

  if ($dCount -eq $sCount -and $dBytes -eq $sBytes) {
    L "  VERIFIED: counts and bytes match exactly. Removing source from C:"
    Remove-Item $src -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path $src) { L "  WARNING: source still present after removal attempt" }
    else { L "  source removed from C:" }
  } else {
    L ("  MISMATCH (files {0} vs {1}, bytes {2} vs {3}) -- SOURCE LEFT ON C: UNTOUCHED" -f $sCount,$dCount,$sBytes,$dBytes)
  }
}

L ""
L ("C: free after: {0:N1} GB" -f ((Get-Volume -DriveLetter C).SizeRemaining/1GB))
L ("D: free after: {0:N1} GB" -f ((Get-Volume -DriveLetter D).SizeRemaining/1GB))
L "=== Archive move finished ==="
