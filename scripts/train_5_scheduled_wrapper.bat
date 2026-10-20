@echo off
REM Wrapper for Task Scheduler: feeds the pause and captures all output.
cd /d "%~dp0.."
call scripts\train_5_characters_overnight.bat <nul > data\train_5_overnight.log 2>&1
