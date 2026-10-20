@echo off
REM Keth v5: rebuilt from the 17 files Barry confirmed, minimal captions.
cd /d "%~dp0.."
call scripts\train_one_v4.bat keth lora_keth_v5 v5 <nul > data\train_keth_v5.log 2>&1
