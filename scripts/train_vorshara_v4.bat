@echo off
REM ---------------------------------------------------------------
REM Vor'Shara v4 -- continues from the APPROVED v3, on the rebuilt
REM 90-frame dataset derived from the 16MP masters.
REM
REM   dataset        : input/lora_vorshara_v4  (90 frames)
REM                    48 rebuilt from masters (21 native-res faces,
REM                    27 body frames, no pillarbox bars)
REM                    + 42 good close-ups carried over from v1's set
REM                    The 27 pillarboxed originals are NOT included --
REM                    they are damaged copies of masters we now have
REM                    clean. Still on disk in lora_vorshara, untouched.
REM   continues from : vorshara_character_v3.safetensors  (the approved one)
REM   writes to      : vorshara_character_v4.safetensors
REM   NEVER touches  : v1, v2, v3
REM
REM Rank MUST stay 16 to line up with v3.
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
echo Vor'Shara v4: 1200 steps, rank 16, lr 1e-4, 90 frames
echo Roughly 3.5 hours. Leave this window OPEN.
echo.

venv\Scripts\python.exe scripts\train_character_loras.py vorshara ^
  --folder lora_vorshara_v4 ^
  --continue-from vorshara_character_v3.safetensors ^
  --steps 1200 ^
  --rank 16 ^
  --tag v4 ^
  --timeout 36000

echo.
echo ==== finished - scroll up for OK or FAILED ====
pause
