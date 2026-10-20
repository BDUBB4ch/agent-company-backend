@echo off
cd /d C:\Users\Owner\Desktop\AgentCompanyBackend
REM stdout goes to its OWN file -- the .bat's redirect LOCKS this handle and
REM python cannot append to the same path (hit live 2026-08-29).
"C:\Users\Owner\Desktop\AgentCompanyBackend\venv\Scripts\python.exe" scripts\rebuild_homes_v4_2026_08_30.py >> data\homes_v4_build.log 2>&1
