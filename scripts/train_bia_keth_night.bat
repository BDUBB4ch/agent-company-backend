@echo off
REM ---------------------------------------------------------------
REM Night run 2026-08-05: the two dataset-fix retrains.
REM
REM   BIA v3   from scratch, folder lora_bia_v3 (42 frames):
REM            the 7 whole turnaround sheets are OUT (they taught the
REM            grid habit behind the fifteen-women render), 5 bleed
REM            edges trimmed and eyeballed, illustration frames
REM            honestly captioned. From scratch because v1 AND v2
REM            both learned the sheet layout.
REM
REM   KETH v3  from scratch, folder lora_keth after the caption fix:
REM            34 drawn panels now say "illustrated character sheet
REM            artwork" so the style stays promptable -- v2's fried
REM            posterized texture was the style binding to @Keth.
REM
REM   1200 steps, rank 16, ~2-3.5h each. Queues behind whatever
REM   ComfyUI is doing (Vor'Shara v5 ends around 18:40).
REM   NEVER touches installed v1/v2 files.
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
echo ==== KETH CAPTION FIX (idempotent) ====
venv\Scripts\python.exe scripts\prepare_keth_v3_captions.py

echo.
echo ==== 1/2 BIA v3 (FROM SCRATCH on cleaned 42-frame set) ====
venv\Scripts\python.exe scripts\train_character_loras.py bia ^
  --folder lora_bia_v3 ^
  --steps 1200 --rank 16 --tag v3 --timeout 43200

echo.
echo ==== 2/2 KETH v3 (FROM SCRATCH on honest captions) ====
venv\Scripts\python.exe scripts\train_character_loras.py keth ^
  --steps 1200 --rank 16 --tag v3 --timeout 43200

echo.
echo ==== NIGHT RUN FINISHED ====
