@echo off
REM Train the remaining characters ONE BY ONE, checkpointed, after Keth v8.
REM
REM Barry, 2026-08-08: "train all one by one, see the results and call it done
REM for now. i can generate my scenes and use it as reference on the new seedance"
REM
REM ONE AT A TIME IS NOT OPTIONAL -- running three at once with no VRAM eviction
REM froze the PC on 2026-08-07. Each python call below also waits for ComfyUI's
REM queue to be empty before it starts, so this is safe even if Keth v8 is still
REM running when this fires.
REM
REM Only pre-flight-clean datasets are queued:
REM   bia      lora_bia_v4              50 frames  0.1% white  OK
REM   tazz     lora_tazz_v4             54 frames  0.0% white  OK
REM   vorshara lora_vorshara_v5_closeups 52 frames 0.1% white  OK
REM NOT queued, and NOT auto-fixed:
REM   yannah   lora_yannah_v3   22 frames over 1024px
REM   bdubb    lora_bdubb       149.9 MPx, over the 120 MPx ceiling
REM The documented fix (normalize_training_images.py) pads to square ON WHITE
REM and overwrites the originals with no backup -- that is the exact mechanism
REM of post-mortem bug 2, where white padding made the LoRA learn nothing.
REM Those two need Barry's call on how to resize, so they are left alone.
cd /d "%~dp0.."

echo ==== FREEING VRAM ====
for /f "skip=1 tokens=1" %%m in ('"%LOCALAPPDATA%\AMD\AI_Bundle\Ollama\ollama.exe" ps 2^>nul') do (
  "%LOCALAPPDATA%\AMD\AI_Bundle\Ollama\ollama.exe" stop %%m 2>nul
)
taskkill /f /im llama-server.exe >nul 2>&1

echo.
echo ======== 1/3  BIA ========
venv\Scripts\python.exe -u scripts\train_character_checkpointed.py bia lora_bia_v4

echo.
echo ======== 2/3  TAZZ ========
venv\Scripts\python.exe -u scripts\train_character_checkpointed.py tazz lora_tazz_v4

echo.
echo ======== 3/3  VORSHARA ========
venv\Scripts\python.exe -u scripts\train_character_checkpointed.py vorshara lora_vorshara_v5_closeups

echo.
echo ==== QUEUE FINISHED - GPU is free again ====
