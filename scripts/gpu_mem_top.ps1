# Who holds the card: dedicated GPU memory per process, biggest first. 2026-10-15.
$ded = Get-Counter '\GPU Process Memory(*)\Dedicated Usage' -ErrorAction SilentlyContinue
$by = @{}
foreach ($x in $ded.CounterSamples) {
    if ($x.InstanceName -match '^pid_(\d+)_') { $p = [int]$Matches[1]; $by[$p] = ($by[$p] + $x.CookedValue) }
}
$by.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 8 | ForEach-Object {
    $n = (Get-Process -Id $_.Key -ErrorAction SilentlyContinue).ProcessName
    "{0,-28} pid {1,-7} {2:N2} GB" -f $n, $_.Key, ($_.Value / 1GB)
}
