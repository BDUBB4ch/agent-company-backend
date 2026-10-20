@echo off
REM ---------------------------------------------------------------
REM Train ONE character LoRA. Usage:  train_one_v4.bat <name> <folder>
REM   e.g.  scripts\train_one_v4.bat keth lora_keth_v4
REM
REM Barry, 2026-08-07: "i meant train 3 characters 1 by 1 not all at the
REM same time. you froze my pc"
REM
REM WHY THE PC FROZE (2026-08-07 17:37 run): scripts\train_batch1_v4.bat
REM went straight to training with NO VRAM EVICTION. Every previous working
REM run (train_bia_keth_night.bat etc.) starts by stopping warm Ollama
REM models first. On a 16GB card, starting SDXL training while an LLM still
REM holds VRAM exhausts the card and takes the desktop down with it.
REM That batch is superseded -- do not use it.
REM
REM This script clears ALL THREE VRAM holders before training:
REM   1. warm Ollama models      (ollama stop, per model)
REM   2. the Bonsai llama-server (port 8811 -- the OLD bats did NOT do this,
REM      and Barry has the global backend set to Bonsai, so it matters now)
REM   3. ComfyUI's resident checkpoint (POST /free)
REM
REM Then trains exactly ONE character and stops. Run the next one yourself
REM when you want the GPU back.
REM ---------------------------------------------------------------
setlocal
cd /d "%~dp0.."

if "%~1"=="" echo Usage: train_one_v4.bat ^<name^> ^<folder^> & exit /b 1
if "%~2"=="" echo Usage: train_one_v4.bat ^<name^> ^<folder^> & exit /b 1

set CHAR=%~1
set FOLDER=%~2
set TAG=%~3
if "%TAG%"=="" set TAG=v4

echo ==== PRE-FLIGHT: dataset size check ====
REM 2026-08-08: the previous run froze the PC and blew a 12h timeout because the
REM dataset carried FULL-RESOLUTION frames (up to 3520x4704, 182 MPx total vs the
REM 12.9 MPx of the set that trained fine). ComfyUI could not fit the latent cache,
REM offloaded to system RAM, and ran at 13.45 s/step instead of ~5.5.
REM This refuses to start rather than repeat that.
venv\Scripts\python.exe scripts\preflight_dataset.py %FOLDER%
if errorlevel 1 (
  echo PRE-FLIGHT FAILED - not training. Run:
  echo   venv\Scripts\python.exe scripts\normalize_training_images.py %FOLDER%
  exit /b 1
)

echo ==== FREEING VRAM BEFORE TRAINING ====

echo   [1/3] stopping warm Ollama models...
for /f "skip=1 tokens=1" %%m in ('"%LOCALAPPDATA%\AMD\AI_Bundle\Ollama\ollama.exe" ps 2^>nul') do (
  echo         stopping %%m
  "%LOCALAPPDATA%\AMD\AI_Bundle\Ollama\ollama.exe" stop %%m 2>nul
)

echo   [2/3] stopping the Bonsai llama-server...
taskkill /f /im llama-server.exe >nul 2>&1
if errorlevel 1 (echo         not running) else (echo         stopped)

echo   [3/3] freeing ComfyUI's resident checkpoint...
curl -s -o nul --max-time 5 http://127.0.0.1:8188/system_stats
if errorlevel 1 (
  echo         ComfyUI not running yet - nothing to free
) else (
  curl -s -o nul --max-time 15 -X POST -H "Content-Type: application/json" ^
    -d "{\"unload_models\":true,\"free_memory\":true}" http://127.0.0.1:8188/free
  echo         freed
)

REM Give the driver a moment to actually release. A keep_alive:0 eviction
REM returns BEFORE the runner hands the VRAM back -- documented behaviour on
REM this machine, see _wait_for_evicted_runners in llm_router.py.
echo   waiting 15s for the driver to release VRAM...
ping -n 16 127.0.0.1 >nul

echo.
echo Checking ComfyUI on 8188...
curl -s -o nul --max-time 10 http://127.0.0.1:8188/system_stats
if not errorlevel 1 goto comfy_up

echo Not running -- starting ComfyUI...
start "ComfyUI" /min cmd /c "cd /d tools\ComfyUI && venv\Scripts\python.exe -u main.py --listen 127.0.0.1 --port 8188 --use-pytorch-cross-attention --reserve-vram 1.5 > ..\..\data\comfyui_train.log 2>&1"

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
echo ==== TRAINING %CHAR% %TAG% from %FOLDER% ====
echo      1200 steps, rank 16, from scratch. Roughly 3-4 hours.
echo.
venv\Scripts\python.exe -u scripts\train_character_loras.py %CHAR% ^
  --folder %FOLDER% ^
  --steps 1200 --rank 16 --tag %TAG% --timeout 43200

echo.
echo ==== %CHAR% %TAG% FINISHED - GPU is free again ====
endlocal
