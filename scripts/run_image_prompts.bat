@echo off
cd /d C:\Users\Owner\Desktop\AgentCompanyBackend
REM --render REMOVED 2026-08-30: Barry switched image generation to his
REM Higgsfield account, which beats local Qwen on every measure this session.
REM This now only asks and writes prompts; Claude generates via the HF MCP.
"C:\Users\Owner\Desktop\AgentCompanyBackend\venv\Scripts\python.exe" scripts\ask_image_prompts_2026_08_30.py >> data\image_prompts_build.log 2>&1
