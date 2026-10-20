@echo off
REM ---------------------------------------------------------------
REM Tazz v3 -- FROM SCRATCH, 2026-08-05.
REM
REM Why from scratch: v1 and v2 both learned "@Tazz = person in
REM tactical gear with braids" because not one of her 29 captions
REM said she is a WOMAN. v2 rendered her as a shirtless muscular
REM man. Barry caught it. Captions are fixed (all 29 now read
REM "@Tazz, a woman, ..."), and a continuation would keep dragging
REM the wrong association along.
REM
REM Every image in lora_tazz was opened 2026-08-05: all photoreal,
REM all female, twin braids, violet/pink double-ring irises. The
REM images were never the problem.
REM
REM 1200 steps, rank 16, tag v3. Queues behind Keth v3 -- ComfyUI
REM serialises jobs, so an overlap just waits its turn.
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
echo ==== TAZZ v3 (FROM SCRATCH, gender restored to captions) ====
venv\Scripts\python.exe scripts\prepare_tazz_v3_captions.py
REM lora_tazz_v3 = Barry's 20 NEW Higgsfield frames (opened and captioned
REM individually 2026-08-05) + her 29 gender-fixed originals = 49.
REM The mirror pass (lora_tazz_aug) is deliberately NOT used: it existed
REM because her old set was ~7 distinct shots repeated, and the new frames
REM include real left AND right profiles, so flipped geometry buys nothing
REM and would reverse the asymmetric chest harness.
venv\Scripts\python.exe scripts\train_character_loras.py tazz ^
  --folder lora_tazz_v3 ^
  --steps 1200 --rank 16 --tag v3 --timeout 43200

echo.
echo ==== TAZZ v3 FINISHED ====
