@echo off
REM Runs ONE character and logs it. Launched via Task Scheduler so it
REM survives the Claude session ending.
cd /d "%~dp0.."
call scripts\train_one_v4.bat bia lora_bia_v4 <nul > data\train_bia_v4.log 2>&1
