@echo off
REM Runs ONE character and logs it. Launched via Task Scheduler so it
REM survives the Claude session ending.
cd /d "%~dp0.."
call scripts\train_one_v4.bat tazz lora_tazz_v4 <nul > data\train_tazz_v4.log 2>&1
