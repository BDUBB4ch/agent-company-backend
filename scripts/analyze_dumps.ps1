$cdb = "C:\Program Files\WindowsApps\Microsoft.WinDbg_1.2610.1001.0_x64__8wekyb3d8bbwe\amd64\cdb.exe"
$root = "C:\Users\Owner\Desktop\AgentCompanyBackend\data"
foreach ($d in Get-ChildItem "$root\crash_dumps\*.dmp") {
  $out = "$root\crash_dumps\analysis\" + $d.BaseName + ".txt"
  & $cdb -z $d.FullName -y "srv*$root\symcache*https://msdl.microsoft.com/download/symbols" -c "!analyze -v; lmvm amdkmdag; q" > $out 2>&1
  "done " + $d.Name
}
