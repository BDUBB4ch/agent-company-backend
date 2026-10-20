@echo off
REM Wrapper for Task Scheduler: feeds the pause and captures all output.
cd /d "%~dp0.."
call scripts\train_batch1_v4.bat <nul > data\train_batch1_v4.log 2>&1
