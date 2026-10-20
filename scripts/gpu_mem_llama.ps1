# Card memory used by the llama-server on port 8811 (dedicated = on the card, shared = spilled to system RAM),
# plus the whole adapter. 2026-10-15, Swift 1.5 trial.
$s = (Get-NetTCPConnection -LocalPort 8811 -State Listen -ErrorAction SilentlyContinue).OwningProcess
$ded = Get-Counter '\GPU Process Memory(*)\Dedicated Usage' -ErrorAction SilentlyContinue
$sha = Get-Counter '\GPU Process Memory(*)\Shared Usage' -ErrorAction SilentlyContinue
$d = ($ded.CounterSamples | Where-Object { $_.InstanceName -like "pid_$($s)_*" } | Measure-Object CookedValue -Sum).Sum
$h = ($sha.CounterSamples | Where-Object { $_.InstanceName -like "pid_$($s)_*" } | Measure-Object CookedValue -Sum).Sum
"llama-server pid $s : dedicated {0:N2} GB, shared (spill) {1:N2} GB" -f ($d / 1GB), ($h / 1GB)
$t = (Get-Counter '\GPU Adapter Memory(*)\Dedicated Usage').CounterSamples | Measure-Object CookedValue -Maximum
"card total in use {0:N2} GB" -f ($t.Maximum / 1GB)
