# Remove AMD Chat and AMD DVR (ReLive / Record & Stream) -- Barry 2026-10-10: "get rid of amd chat and that relive thing too".
# Both are MSI products registered under Adrenalin; msiexec /X by product code, quiet. Runs elevated once.
$log = 'C:\Users\Owner\Desktop\AgentCompanyBackend\data\amd_chat_relive_remove_2026_10_10.log'
function Note($m) { "$(Get-Date -Format 'HH:mm:ss') $m" | Add-Content $log; Write-Output $m }
"== AMD Chat + DVR removal $(Get-Date) ==" | Set-Content $log

foreach ($pn in 'AMDChat', 'AMDRSSrcExt') {
    $r = Get-Process -Name $pn -ErrorAction SilentlyContinue
    if ($r) { $r | Stop-Process -Force -ErrorAction SilentlyContinue; Note "stopped running: $pn" }
}

$products = @(
    @{ name = 'AMD Chat'; code = '{E107EA24-CCCB-4393-BEDD-B663E00F6545}' },
    @{ name = 'AMD DVR (ReLive / Record & Stream)'; code = '{82B67D1C-33CB-46FF-A3DC-E7BE6902D38A}' }
)
foreach ($p in $products) {
    try {
        $x = Start-Process -FilePath 'msiexec.exe' -ArgumentList "/X$($p.code) /qn /norestart" -Wait -PassThru -ErrorAction Stop
        Note "$($p.name): msiexec exit $($x.ExitCode) (0 = removed, 3010 = removed, reboot pending, 1605 = not installed)"
    } catch { Note "$($p.name): FAILED $($_.Exception.Message)" }
}

$left = (Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*', 'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -in 'AMD Chat', 'AMD DVR' }).DisplayName
Note ("still registered: " + $(if ($left) { $left -join ', ' } else { 'none' }))
Note ("files: AMDChat exe present = " + (Test-Path 'C:\Program Files\AMD\AMDChat\amdchat.exe') + "; AMDRSSrcExt exe present = " + (Test-Path 'C:\Program Files\AMD\CNext\CNext\AMDRSSrcExt.exe'))
Note "done"
