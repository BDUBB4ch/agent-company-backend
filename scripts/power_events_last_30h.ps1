# Read-only: sleep / resume / boot events from the System log, last 30h.
# Why (2026-09-04): Barry -- "i went to bed and left you running and woke up to
# my pc on standby... it happens every time i leave you over night." Overnight
# GPU work dies with the sleep timer; this shows exactly when it fired.
$ids = 42, 107, 1, 41, 6005, 6006, 6008, 12, 13, 506, 507
Get-WinEvent -FilterHashtable @{LogName = 'System'; Id = $ids } -MaxEvents 60 -ErrorAction SilentlyContinue |
    Where-Object { $_.TimeCreated -gt (Get-Date).AddHours(-30) } |
    Sort-Object TimeCreated |
    ForEach-Object {
        $first = ($_.Message -split "`n")[0]
        if ($first.Length -gt 100) { $first = $first.Substring(0, 100) }
        '{0}  id={1,-4} {2}  {3}' -f $_.TimeCreated.ToString('MM-dd HH:mm:ss'), $_.Id, $_.ProviderName, $first
    }
