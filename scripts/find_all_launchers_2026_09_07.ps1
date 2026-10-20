# Read-only. Finds EVERY shortcut or .bat anywhere that launches the office,
# the dashboard, or MyStudio -- Desktop, Start Menu, Startup, taskbar pins.
# Barry, 2026-09-07: "i should only have 1 launcher. there should be no others"
$sh = New-Object -ComObject WScript.Shell

$paths = @(
  "$env:USERPROFILE\Desktop",
  "$env:APPDATA\Microsoft\Windows\Start Menu\Programs",
  "$env:ProgramData\Microsoft\Windows\Start Menu\Programs",
  "$env:APPDATA\Microsoft\Internet Explorer\Quick Launch",
  "$env:APPDATA\Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar",
  "$env:PUBLIC\Desktop"
)

$pattern = 'AgentDashboard|AgentCompanyBackend|MyStudio|Start Everything|Start My Studio|Studio\.bat|8765'

foreach ($p in $paths) {
  if (-not (Test-Path $p)) { continue }
  Get-ChildItem -Path $p -Include *.lnk, *.bat -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object {
    $target = if ($_.Extension -eq '.lnk') { $sh.CreateShortcut($_.FullName).TargetPath } else { $_.FullName }
    if ($target -match $pattern) {
      Write-Output ("FOUND : " + $_.Name)
      Write-Output ("  in  : " + $_.DirectoryName)
      Write-Output ("  ->  : " + $target)
      Write-Output ""
    }
  }
}
Write-Output "--- scan complete ---"
