@echo off
cd /d C:\Users\Owner\Desktop\AgentCompanyBackend
:wait
tasklist /FI "IMAGENAME eq python.exe" /FO CSV | find /I "python.exe" >nul
venv\Scripts\python.exe -c "import os,sys,time; sys.exit(0 if not os.path.exists(r'data\video_rendering.flag') else 1)"
if errorlevel 1 (
  timeout /t 30 /nobreak >nul
  goto wait
)
venv\Scripts\python.exe scripts\fix_amara_face_v2_2026_08_29.py >> data\amara_v2.log 2>&1
