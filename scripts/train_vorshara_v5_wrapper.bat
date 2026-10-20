@echo off
REM Task Scheduler wrapper: captures all output, no console input needed.
cd /d "%~dp0.."
call scripts\train_vorshara_v5_curriculum.bat > data\train_vorshara_v5.log 2>&1
