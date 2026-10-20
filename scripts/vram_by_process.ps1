# VRAM per process (dedicated + shared, GB), biggest first. 2026-10-09.
$d = (Get-Counter '\GPU Process Memory(*)\Dedicated Usage' -ErrorAction SilentlyContinue).CounterSamples
$s = (Get-Counter '\GPU Process Memory(*)\Shared Usage' -ErrorAction SilentlyContinue).CounterSamples
$rows = foreach ($x in $d) {
    if ($x.CookedValue -gt 100MB) {
        $p = ($x.InstanceName -replace '.*pid_(\d+).*', '$1')
        $sh = ($s | Where-Object { $_.InstanceName -eq $x.InstanceName }).CookedValue
        $n = (Get-Process -Id $p -ErrorAction SilentlyContinue).ProcessName
        [pscustomobject]@{ proc = $n; pid = $p; dedicated_gb = [math]::Round($x.CookedValue / 1GB, 2); shared_gb = [math]::Round($sh / 1GB, 2) }
    }
}
$rows | Sort-Object dedicated_gb -Descending | Format-Table -AutoSize
$tot = ($rows | Measure-Object dedicated_gb -Sum).Sum
"TOTAL dedicated: {0:N2} GB" -f $tot
