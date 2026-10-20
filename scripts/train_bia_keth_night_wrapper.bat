@echo off
REM Task Scheduler wrapper: captures all output, no console input needed.
cd /d "%~dp0.."
call scripts\train_bia_keth_night.bat > data\train_bia_keth_night.log 2>&1
