#!/usr/bin/env bash
# Derek's redraft (with the new back-to-back check) once the motion test is off the card. 2026-10-02.
cd /c/Users/Owner/Desktop/AgentCompanyBackend
while powershell -NoProfile -Command "exit [int]((Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -match 'motion_test_2026_10_02' }).Count -eq 0)"; do sleep 30; done
echo "motion test done $(date +%H:%M:%S)"
venv/Scripts/python.exe scripts/derek_redraft_2026_10_02.py
