@echo off
REM ---------------------------------------------------------------
REM Bia v4 -- FROM SCRATCH, 2026-08-06.
REM
REM v3 (finished 23:34) fixed her GRID problem -- the 7 whole
REM turnaround sheets are out -- but not one of its 42 captions
REM mentioned her eyes, and her source frames disagree with each
REM other on iris colour. Nothing anchored her face.
REM
REM v4 fixes exactly that:
REM   - Barry's 11 Eye Lock frames (opened individually): deep-purple
REM     double ring around a hazel-green/gold iris, gold skin spots,
REM     iridescent shimmer on the TEMPLES specifically
REM   - his canon anchor written into all 53 captions
REM
REM From scratch because v1/v2/v3 all learned her without an eye
REM anchor; continuing would drag that along.
REM
REM 1200 steps, rank 16, tag v4. Queues behind Yannah v3.
REM ---------------------------------------------------------------
cd /d "%~dp0.."

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
echo ComfyUI did not come up -- check data\comfyui.log
exit /b 1

:comfy_up
echo.
echo ==== BIA v4 (FROM SCRATCH, Eye Lock frames + canon captions) ====
venv\Scripts\python.exe scripts\build_bia_v4_dataset.py
venv\Scripts\python.exe scripts\apply_bia_canon_captions.py lora_bia_v4
venv\Scripts\python.exe scripts\train_character_loras.py bia ^
  --folder lora_bia_v4 ^
  --steps 1200 --rank 16 --tag v4 --timeout 43200

echo.
echo ==== BIA v4 FINISHED ====
