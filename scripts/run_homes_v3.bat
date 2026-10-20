@echo off
cd /d C:\Users\Owner\Desktop\AgentCompanyBackend
venv\Scripts\python.exe scripts\rebuild_agent_homes_v3_2026_08_29.py >> data\homes_v3_build.log 2>&1
