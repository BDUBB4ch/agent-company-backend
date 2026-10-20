@echo off
REM Keth v6: v5 dataset with the white padding removed (28.5%% -> 0.3%%).
cd /d "%~dp0.."
call scripts\train_one_v4.bat keth lora_keth_v5 v6 <nul > data\train_keth_v6.log 2>&1
