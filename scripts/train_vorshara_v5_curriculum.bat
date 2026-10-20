@echo off
REM ---------------------------------------------------------------
REM Vor'Shara v5 -- Barry's curriculum order (2026-08-04):
REM "close ups should be the first thing that gets trained. then
REM the body or something."
REM
REM   Stage 1: 52 close-up frames, 800 steps, continues from the
REM            installed v4 -> installs vorshara_character_v5a
REM   Stage 2: 38 body frames, 400 steps, continues from v5a
REM            -> installs vorshara_character_v5
REM
REM   Lopsided 800/400 on purpose: whatever trains LAST is what the
REM   weights end nearest to, and the FACE is the failing part --
REM   so the face gets the long run and the body gets a short tail.
REM   Rank stays 16 (must match v4). NEVER touches v1-v4.
REM
REM   Folders were built by scripts/prepare_vorshara_v5.py from a
REM   frame-by-frame visual sort (data/vorshara_v5_sort.txt).
REM   Scheduled behind the 5-character run; ComfyUI queues jobs, so
REM   even an overlap just waits its turn (timeouts sized for it).
REM ---------------------------------------------------------------
cd /d "%~dp0.."

echo Evicting any warm Ollama models...
for /f "skip=1 tokens=1" %%m in ('"%LOCALAPPDATA%\AMD\AI_Bundle\Ollama\ollama.exe" ps 2^>nul') do (
  "%LOCALAPPDATA%\AMD\AI_Bundle\Ollama\ollama.exe" stop %%m 2>nul
)

echo Checking ComfyUI on 8188...
curl -s -o nul --max-time 10 http://127.0.0.1:8188/system_stats
if not errorlevel 1 goto comfy_up

echo Not running -- starting ComfyUI...
start "ComfyUI" /min cmd /c "cd /d tools\ComfyUI && venv\Scripts\python.exe main.py --listen 127.0.0.1 --port 8188 --use-pytorch-cross-attention --reserve-vram 1.5"

set tries=0
:wait_comfy
ping -n 6 127.0.0.1 >nul
curl -s -o nul --max-time 5 http://127.0.0.1:8188/system_stats
if not errorlevel 1 goto comfy_up
set /a tries+=1
if %tries% lss 24 goto wait_comfy
echo ComfyUI did not come up after 2 minutes -- check data\comfyui.log
exit /b 1

:comfy_up
echo.
echo ==== STAGE 1/2: CLOSE-UPS (52 frames, 800 steps, from v4) ====
venv\Scripts\python.exe scripts\train_character_loras.py vorshara ^
  --folder lora_vorshara_v5_closeups ^
  --continue-from vorshara_character_v4.safetensors ^
  --steps 800 --rank 16 --tag v5a --timeout 43200

echo.
echo ==== STAGE 2/2: BODY (38 frames, 400 steps, from v5a) ====
venv\Scripts\python.exe scripts\train_character_loras.py vorshara ^
  --folder lora_vorshara_v5_body ^
  --continue-from vorshara_character_v5a.safetensors ^
  --steps 400 --rank 16 --tag v5 --timeout 43200

echo.
echo ==== VORSHARA V5 CURRICULUM FINISHED ====
