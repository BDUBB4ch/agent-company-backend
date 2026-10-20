$name   = 'ArchiveMoveSD'
$script = 'C:\Users\Owner\Desktop\AgentCompanyBackend\scripts\archive_move_sd_2026_09_06.ps1'

schtasks /delete /TN $name /F 2>&1 | Out-Null

$action    = New-ScheduledTaskAction -Execute 'powershell.exe' `
             -Argument ('-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $script)
$trigger   = New-ScheduledTaskTrigger -Once -At (Get-Date).AddYears(1)
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
             -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 6) `
             -StartWhenAvailable
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger `
  -Settings $settings -Description 'One-shot: resume Archive move to D:. Self-deletes.' | Out-Null

Start-ScheduledTask -TaskName $name
Start-Sleep -Seconds 5
Get-ScheduledTask -TaskName $name | Select-Object TaskName, State | Format-Table -AutoSize
