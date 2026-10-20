@echo off
REM Keth v8: checkpointed run -- 8 segments x 150 iterations, grad_acc=4.
REM See scripts\train_keth_v8_checkpointed.py for why (ComfyUI trainer is
REM run-to-run unstable: unseeded image order + unseeded noise level, batch 1,
REM no gradient clipping, no LR schedule).
REM
REM Same VRAM eviction as train_one_v4.bat -- all three holders, in order.
cd /d "%~dp0.."

echo ==== PRE-FLIGHT ====
venv\Scripts\python.exe scripts\preflight_dataset.py lora_keth_v5
if errorlevel 1 (
  echo PRE-FLIGHT FAILED - not training.
  exit /b 1
)

echo ==== FREEING VRAM ====
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
  echo         ComfyUI not running yet - starting it
  start "ComfyUI" /min cmd /c "cd /d tools\ComfyUI && venv\Scripts\python.exe -u main.py --listen 127.0.0.1 --port 8188 --use-pytorch-cross-attention --reserve-vram 1.5 > ..\..\data\comfyui_train.log 2>&1"
  ping -n 31 127.0.0.1 >nul
) else (
  curl -s -o nul --max-time 15 -X POST -H "Content-Type: application/json" ^
    -d "{\"unload_models\":true,\"free_memory\":true}" http://127.0.0.1:8188/free
  echo         freed
)
echo   waiting 15s for the driver to release VRAM...
ping -n 16 127.0.0.1 >nul

echo.
echo ==== KETH v8 CHECKPOINTED TRAINING ====
venv\Scripts\python.exe -u scripts\train_keth_v8_checkpointed.py

echo.
echo ==== keth v8 FINISHED - GPU is free again ====
