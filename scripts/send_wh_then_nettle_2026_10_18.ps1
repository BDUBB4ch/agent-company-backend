# 2026-10-18 22:10: Witch Hazel is written and checked but never SENT (her turns run out of tool calls on re-checks).
# Turn 1: send it, nothing else. Turns 2-5: the Nettle redo (start, parts, check, send). Log: data/send_wh_then_nettle.log
$root = Split-Path -Parent $PSScriptRoot
$log = Join-Path $root 'data\send_wh_then_nettle_2026_10_18.log'
function Say($m) { ("" + (Get-Date -Format 'HH:mm:ss') + " " + $m) | Tee-Object -FilePath $log -Append }
function Ask($m) {
  $body = @{agent_id='ilnora'; office=$true; task=$true; activity='sending her redos'; message=$m} | ConvertTo-Json -Compress
  try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8420/api/chat' -Method Post -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) -TimeoutSec 1500
        Say ("reply: " + (("" + $r.reply) -replace "`n"," ").Substring(0, [Math]::Min(260, ("" + $r.reply).Length))) }
  catch { Say ("turn failed: " + $_.Exception.Message) }
}
function Queued { Get-ChildItem (Join-Path $root 'data\video_queue\job_*.json') | ForEach-Object { Get-Content $_ -Raw -Encoding UTF8 | ConvertFrom-Json } | Where-Object { $_.status -in @('queued','building') } | ForEach-Object { $_.pkg.title } }
Ask "One tool call this turn and nothing else: video_draft action send -- Witch Hazel is checked clean and only the send is missing. Do not re-check, do not rewrite. Send it."
Say ("in line: " + ((Queued) -join ' | '))
$nettle = @(
 "Witch Hazel is in the line. Now the Stinging Nettle redo -- and to be exact: the Nettle on Barry's desk is the FIRST build, the one with the wrong plant in parts 1, 4, 5 and 6; no redo of it exists yet. This turn: video_draft action start, redo of the same title 'Stinging Nettle — The Weed That Stings You and Feeds You', then add_parts with your original words part for part, parts 1 through 4. In parts 1 and 4 write the plant as a plain portrait of the real plant (Urtica dioica: simple ovate serrated leaves in opposite pairs on a square stem, fine stinging hairs, drooping green flower strings) so the builder uses the real photo. Stop after part 4.",
 "Continue the Nettle redo: add_parts 5 through 8, your original words, parts 5 and 6 as plain portraits of the real plant (Urtica dioica, as before). Then action check.",
 "Nettle: fix only what the check named (if anything), then action send. Nothing else this turn.",
 "If Nettle is still a draft: action send now."
)
foreach ($m in $nettle) {
  Ask $m
  $q = Queued; Say ("in line: " + ($q -join ' | '))
  if ($q -match 'Nettle') { Say 'nettle sent'; break }
  Start-Sleep -Seconds 20
}
Say 'done'
