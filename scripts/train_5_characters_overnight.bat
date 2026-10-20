@echo off
REM ---------------------------------------------------------------
REM All 5 remaining characters, sequential  (2026-08-04)
REM Vor'Shara is NOT here -- she is already at v4.
REM
REM   bdubb   143 imgs  continue-from-v1  (captions fixed since v1:
REM                     24 wrong-hat + 6 wrong-garment now honest)
REM   bia      49 imgs  continue-from-v1  (Tazz file + no-character
REM                     plates gone, 062 iris ref weighted 6x)
REM   yannah   37 imgs  continue-from-v1  (bad batch 000-003 gone --
REM                     swirls and violet eyes were those 4 frames)
REM   keth     41 imgs  continue-from-v1  (v1 saw only 7 frames;
REM                     rebuilt set is 41 split panels)
REM   tazz     29 imgs  FROM SCRATCH      (v1 trained on whole
REM                     multi-panel composites -- the exact failure
REM                     that broke the first B Dubb LoRA. Clean
REM                     split panels start fresh.)
REM
REM   1200 steps each, rank 16 (MUST stay 16 to line up with v1),
REM   tag v2 -> installs as <name>_character_v2.safetensors.
REM   NEVER touches the existing <name>_character.safetensors.
REM
REM   ~10.1 s/step measured -> roughly 3.4 h per character,
REM   ~17 HOURS TOTAL. Start it at night, let it run through the
REM   day. Each character installs as soon as it finishes, so an
REM   early stop only loses the characters not yet reached.
REM   Order: bdubb first (best dataset), tazz last (the gamble).
REM
REM   Leave the agents alone while this runs -- a chat message makes
REM   the backend free ComfyUI's VRAM mid-training.
REM ---------------------------------------------------------------
cd /d "%~dp0.."

echo Evicting any warm Ollama models (they hold VRAM the trainer needs)...
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
timeout /t 5 /nobreak >nul
curl -s -o nul --max-time 5 http://127.0.0.1:8188/system_stats
if not errorlevel 1 goto comfy_up
set /a tries+=1
if %tries% lss 24 goto wait_comfy
echo ComfyUI did not come up after 2 minutes -- check data\comfyui.log
pause
exit /b 1

:comfy_up
echo.
echo ==== 1/5 B DUBB (continue-from-v1, 1200 steps, ~3.4h) ====
venv\Scripts\python.exe scripts\train_character_loras.py bdubb ^
  --continue-from-v1 --steps 1200 --rank 16 --tag v2 --timeout 36000

echo.
echo ==== 2/5 BIA (continue-from-v1, 1200 steps, ~3.4h) ====
venv\Scripts\python.exe scripts\train_character_loras.py bia ^
  --continue-from-v1 --steps 1200 --rank 16 --tag v2 --timeout 36000

echo.
echo ==== 3/5 YANNAH (continue-from-v1, 1200 steps, ~3.4h) ====
venv\Scripts\python.exe scripts\train_character_loras.py yannah ^
  --continue-from-v1 --steps 1200 --rank 16 --tag v2 --timeout 36000

echo.
echo ==== 4/5 KETH (continue-from-v1, 1200 steps, ~3.4h) ====
venv\Scripts\python.exe scripts\train_character_loras.py keth ^
  --continue-from-v1 --steps 1200 --rank 16 --tag v2 --timeout 36000

echo.
echo ==== 5/5 TAZZ (FROM SCRATCH on split panels, 1200 steps, ~3.4h) ====
venv\Scripts\python.exe scripts\train_character_loras.py tazz ^
  --steps 1200 --rank 16 --tag v2 --timeout 36000

echo.
echo ==== ALL 5 FINISHED - scroll up for OK or FAILED per character ====
pause
