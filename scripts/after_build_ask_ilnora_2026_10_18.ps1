# 2026-10-18: when Henbane's redo build is over (reel_building.flag + video_rendering.flag both down), give Ilnora up to
# three turns to send Witch Hazel (part 7 needs plant: Hamamelis virginiana) and write + send the Nettle redo. No restart.
$root = Split-Path -Parent $PSScriptRoot
$log = Join-Path $root 'data\after_build_ask_ilnora_2026_10_18.log'
function Say($m) { ("" + (Get-Date -Format 'HH:mm:ss') + " " + $m) | Tee-Object -FilePath $log -Append }
$flag = Join-Path $root 'data\video_rendering.flag'; $mark = Join-Path $root 'data\reel_building.flag'
$deadline = (Get-Date).AddHours(6)
while ((Test-Path $flag) -or (Test-Path $mark)) { if ((Get-Date) -gt $deadline) { Say 'gave up'; exit 1 }; Start-Sleep -Seconds 60 }
Start-Sleep -Seconds 90      # the proofread and the folder copy finish after the mark drops
Say 'build over'
$msgs = @(
 "Henbane's redo build is finished and the card is free. Two things left, in this turn: 1) Witch Hazel -- give part 7 plant: Hamamelis virginiana (your own finding), check, send. 2) Stinging Nettle -- start the redo of the same title, your original words part for part, parts 1, 4, 5 and 6 with the plant written so it cannot be mistaken (Urtica dioica: simple ovate serrated leaves in opposite pairs on a square stem, fine stinging hairs, drooping green flower strings), check, send.",
 "Carry on where you stopped: whichever of Witch Hazel and the Stinging Nettle redo is not yet in the line -- finish it (check, send) in this turn.",
 "Last push: check and send whatever of Witch Hazel / Stinging Nettle is still a draft."
)
foreach ($m in $msgs) {
  $body = @{agent_id='ilnora'; office=$true; task=$true; activity='sending her redos'; message=$m} | ConvertTo-Json -Compress
  try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8420/api/chat' -Method Post -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) -TimeoutSec 1500
        Say ("reply: " + (("" + $r.reply) -replace "`n"," ").Substring(0, [Math]::Min(300, ("" + $r.reply).Length))) }
  catch { Say ("turn failed: " + $_.Exception.Message) }
  $queued = Get-ChildItem (Join-Path $root 'data\video_queue\job_*.json') | ForEach-Object { Get-Content $_ -Raw -Encoding UTF8 | ConvertFrom-Json } | Where-Object { $_.status -in @('queued','building') } | ForEach-Object { $_.pkg.title }
  Say ("in line/building now: " + ($queued -join ' | '))
  if (($queued -match 'Witch Hazel') -and ($queued -match 'Nettle')) { Say 'both sent'; break }
  Start-Sleep -Seconds 30
}
Say 'done'
