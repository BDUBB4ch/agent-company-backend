REM SUPERSEDED 2026-08-07 -- DO NOT RUN.
REM No VRAM eviction: it froze the PC on the 17:37 run. Use scripts\train_one_v4.bat
REM one character at a time instead. Kept only for the record.
exit /b 1
@echo off
REM ---------------------------------------------------------------
REM BATCH 1 v4 -- Keth, Bia, Tazz.  Built 2026-08-07.
REM
REM Datasets were prepared by hand this session and are ALREADY ON DISK:
REM   tools\ComfyUI\input\lora_keth_v4   55 frames
REM   tools\ComfyUI\input\lora_bia_v4    50 frames
REM   tools\ComfyUI\input\lora_tazz_v4   49 frames
REM
REM *** THIS SCRIPT DELIBERATELY DOES NOT REBUILD ANY DATASET. ***
REM scripts\train_bia_v4.bat (2026-08-06) calls build_bia_v4_dataset.py +
REM apply_bia_canon_captions.py, which would OVERWRITE lora_bia_v4 with the
REM older set. Do not run that one. Use this.
REM
REM What is different about these sets (the corrected root cause):
REM   every caption describes what is ACTUALLY IN THAT FRAME. The old sets
REM   pasted the full canon spec onto every frame regardless of content --
REM   e.g. "small low-profile ears" on Keth panels showing flared ears --
REM   which taught the wrong mapping.
REM
REM Per-character rulings baked into the captions:
REM   KETH  ears = spec (small, low-profile). Aug-6 flared-ear close-ups are
REM         used ONLY as cropped eyes, ears physically outside the frame.
REM   BIA   iris reference 023953, broad beaded deep-purple ring. Flecks on
REM         temples AND cheeks (Barry reversed temples-only on 2026-08-07).
REM   TAZZ  Aug-6 purpose-built shoot carries identity, fixes the v2 gender
REM         collapse. Coloured suits excluded.
REM
REM From scratch (no --continue-from): every previous version learned these
REM characters from mis-captioned data, so continuing would drag that along.
REM 1200 steps, rank 16, tag v4. ~3.5h each, ~10-11h total.
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
echo ==== 1/3 KETH v4 (55 frames: May-10 originals + Aug-6 eye crops) ====
venv\Scripts\python.exe scripts\train_character_loras.py keth ^
  --folder lora_keth_v4 ^
  --steps 1200 --rank 16 --tag v4 --timeout 43200

echo.
echo ==== 2/3 BIA v4 (50 frames: Aug-6 batch + 11 native-res iris crops) ====
venv\Scripts\python.exe scripts\train_character_loras.py bia ^
  --folder lora_bia_v4 ^
  --steps 1200 --rank 16 --tag v4 --timeout 43200

echo.
echo ==== 3/3 TAZZ v4 (49 frames: Aug-6 shoot + iris crops + split May-7) ====
REM Tazz v3 died with HIP OOM at 49 images. Same count here, so if it OOMs
REM again the fix is fewer steps or a smaller batch, NOT more images.
venv\Scripts\python.exe scripts\train_character_loras.py tazz ^
  --folder lora_tazz_v4 ^
  --steps 1200 --rank 16 --tag v4 --timeout 43200

echo.
echo ==== BATCH 1 FINISHED -- scroll up for OK or FAILED per character ====
