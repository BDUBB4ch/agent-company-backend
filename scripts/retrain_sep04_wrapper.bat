@echo off
REM Task Scheduler / Startup wrapper for the 2026-09-04 character retrain
REM (survives the Claude session; the proven overnight pattern). Resumable:
REM re-run to continue. Per-launch log name: a .bat redirect LOCKS its file,
REM so a second launch against one shared log died with "cannot access the
REM file" instead of reaching the runner's own refuse-if-running check.
cd /d "C:\Users\Owner\Desktop\AgentCompanyBackend"
"venv\Scripts\python.exe" "scripts\train_characters_034_2026_09_04.py" >> "data\retrain_2026-09-04\wrapper_%RANDOM%.log" 2>&1
