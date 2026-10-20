@echo off
REM ---------------------------------------------------------------
REM Vor'Shara LoRA -- continuation run off the WORKING v1 weights.
REM
REM   continues from : vorshara_character_400_steps_v1.safetensors
REM                    (byte-identical frozen copy of the installed v1)
REM   writes to      : vorshara_character_v3.safetensors
REM   NEVER touches  : vorshara_character.safetensors  (live @Vorshara)
REM                    vorshara_character_v2.safetensors (backup)
REM
REM Rank MUST stay 16 -- it has to match v1 or the tensors will not line up.
REM ---------------------------------------------------------------
cd /d "%~dp0.."

echo Checking ComfyUI on 8188...
curl -s -o nul --max-time 10 http://127.0.0.1:8188/system_stats
if errorlevel 1 (
  echo.
  echo ComfyUI is NOT running on 8188. Start it, then re-run this file.
  pause
  exit /b 1
)

echo.
echo Starting Vor'Shara continuation: 1200 steps, rank 16, lr 1e-4
echo Expect roughly 3.5 hours. Leave this window OPEN.
echo.

venv\Scripts\python.exe scripts\train_character_loras.py vorshara ^
  --continue-from-v1 ^
  --steps 1200 ^
  --rank 16 ^
  --tag v3 ^
  --timeout 36000

echo.
echo ==== finished - scroll up for OK or FAILED ====
pause
