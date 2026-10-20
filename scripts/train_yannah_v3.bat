@echo off
REM ---------------------------------------------------------------
REM Yannah v3 -- FROM SCRATCH, 2026-08-06. Barry asked to redo her.
REM
REM Why from scratch: v1 and v2 both trained on 37 frames of which
REM THIRTEEN were multi-panel composites (main portrait + thumbnail
REM figures, four-panel sheets, two-figure layouts), and every single
REM caption was the same dead boilerplate -- "@Yannah, character
REM sheet panel, plain studio background". No gender word, no canon
REM features, and false for most frames. A continuation would drag
REM all of that along.
REM
REM lora_yannah_v3 = her 24 clean single-subject frames, each
REM captioned from what is actually in it (opened at full resolution
REM 2026-08-05): named a woman, gold freckle SPOTS, hazel green-brown
REM eyes, shaved-undercut curly hair, teal-piped suit, pose and
REM background described so only her face binds to @Yannah.
REM
REM The 13 composites are EXCLUDED, not deleted -- they still sit in
REM lora_yannah and can be split into single panels later.
REM
REM 1200 steps, rank 16, tag v3. Queues behind Tazz v3.
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
echo ==== YANNAH v3 (FROM SCRATCH, 24 clean frames, honest captions) ====
venv\Scripts\python.exe scripts\build_yannah_v3_dataset.py
venv\Scripts\python.exe scripts\apply_canon_anchors.py yannah lora_yannah_v3
REM Barry's 22 new Higgsfield frames, opened and captioned individually
REM 2026-08-06: true left AND right profiles, a low-angle, three expressions,
REM a running shot and three real environments -- coverage her old set never had.
venv\Scripts\python.exe scripts\add_new_yannah_frames.py
venv\Scripts\python.exe scripts\train_character_loras.py yannah ^
  --folder lora_yannah_v3 ^
  --steps 1200 --rank 16 --tag v3 --timeout 43200

echo.
echo ==== YANNAH v3 FINISHED ====
