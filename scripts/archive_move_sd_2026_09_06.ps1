$ErrorActionPreference = 'Continue'
$log = 'C:\Users\Owner\Desktop\AgentCompanyBackend\data\archive_move_2026-09-06.log'
function L($m) { Add-Content $log ("[{0}] {1}" -f (Get-Date -f 'HH:mm:ss'), $m) }

$src = 'C:\Users\Owner\Desktop\Archive\sd safe tensor'
$dst = 'D:\Archive\sd safe tensor'

# refuse to double-run
if (Get-Process robocopy -ErrorAction SilentlyContinue) {
  L "RESUME ABORT: a robocopy is already running"; exit 0
}

L ""
L "=== RESUME (scheduled task) : sd safe tensor ==="
if (-not (Test-Path $src)) { L "  source already gone -- nothing to do"; exit 0 }

$sf = Get-ChildItem $src -Recurse -File -Force -ErrorAction SilentlyContinue
$sCount = $sf.Count; $sBytes = ($sf | Measure-Object Length -Sum).Sum
L ("  source: {0} files, {1:N0} bytes ({2:N2} GB)" -f $sCount, $sBytes, ($sBytes/1GB))

# /E resumes: identical files already at dest are skipped
robocopy $src $dst /E /R:1 /W:1 /NFL /NDL /NP /NJH /NJS | Out-Null
$rc = $LASTEXITCODE
L "  robocopy exit code: $rc  (0-7 = ok, 8+ = error)"

$df = Get-ChildItem $dst -Recurse -File -Force -ErrorAction SilentlyContinue
$dCount = $df.Count; $dBytes = ($df | Measure-Object Length -Sum).Sum
L ("  dest  : {0} files, {1:N0} bytes ({2:N2} GB)" -f $dCount, $dBytes, ($dBytes/1GB))

if ($rc -lt 8 -and $dCount -eq $sCount -and $dBytes -eq $sBytes) {
  L "  VERIFIED: counts and bytes match exactly. Removing source from C:"
  Remove-Item $src -Recurse -Force -ErrorAction SilentlyContinue
  if (Test-Path $src) { L "  WARNING: source still present" } else { L "  source removed from C:" }
} else {
  L "  NOT VERIFIED -- SOURCE LEFT ON C: UNTOUCHED (re-run to resume)"
}

L ("C: free after: {0:N1} GB" -f ((Get-Volume -DriveLetter C).SizeRemaining/1GB))
L ("D: free after: {0:N1} GB" -f ((Get-Volume -DriveLetter D).SizeRemaining/1GB))
L "=== RESUME finished ==="

# self-clean: never leave a scheduled task behind to re-fire later
schtasks /delete /TN ArchiveMoveSD /F 2>&1 | Out-Null
L "scheduled task ArchiveMoveSD deleted"
