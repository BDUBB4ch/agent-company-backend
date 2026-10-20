@echo off
REM Task Scheduler wrapper: captures all output, no console input needed.
cd /d "%~dp0.."
call scripts\train_bia_v4.bat > data\train_bia_v4.log 2>&1
