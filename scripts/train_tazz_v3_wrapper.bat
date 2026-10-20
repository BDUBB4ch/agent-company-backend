@echo off
REM Task Scheduler wrapper: captures all output, no console input needed.
cd /d "%~dp0.."
call scripts\train_tazz_v3.bat > data\train_tazz_v3.log 2>&1
