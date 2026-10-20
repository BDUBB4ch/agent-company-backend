@echo off
REM ============================================================
REM ALL SIX CHARACTERS, ONE AT A TIME, CHECKPOINTED.
REM Barry, 2026-08-09: "I want all me characters trained even Yannah and
REM B Dubb. what ever you have to do, but dont break them."
REM
REM RECIPE (unchanged from the v5 run that produced a good Keth):
REM   1200 steps, rank 16, lr 1e-4, grad_acc 1, batch 1.
REM   Split into 8 segments of 150 ONLY for visibility -- each segment saves a
REM   checkpoint and renders a test image, so a bad run is visible in ~30 min
REM   instead of 4 hours, and there are 8 checkpoints to choose from.
REM
REM THE ONE REAL FIX: gradient clipping, patched into ComfyUI's trainer at
REM   tools/ComfyUI/comfy_extras/nodes_train.py (see the LOCAL PATCH comment).
REM   Validated 2026-08-09 on a 30-step run: trained and saved cleanly.
REM   Stock file backed up to data/backup_nodes_train_before_clip_2026-08-09.py.
REM   A ComfyUI UPDATE WILL WIPE THIS PATCH.
REM
REM ONE AT A TIME IS NOT OPTIONAL -- three at once with no VRAM eviction froze
REM the PC on 2026-08-07. Each python call also waits for ComfyUI's queue to be
REM empty before starting.
REM
REM DATASETS (all pre-flight clean, all built from Barry's originals):
REM   keth     lora_keth_v5    65 frames  0.3% white
REM   bia      lora_bia_v4     50 frames  0.1% white
REM   tazz     lora_tazz_v4    54 frames  0.0% white
REM   vorshara lora_vorshara_v5_closeups  52 frames  0.1% white
REM   yannah   lora_yannah_v4  22 frames  0.1% white  <- NEW, from "New Yannah.zip"
REM   bdubb    lora_bdubb_v4   22 frames  2.6% white  <- NEW, today's renders
REM Yannah and B Dubb were built by scripts/build_dataset_downscale_only.py:
REM DOWNSCALE ONLY to a 1024 long edge, aspect preserved, NO white padding, NO
REM crop, originals never touched. Both came out uniform 760x1024.
REM
REM ~4.3h per character, ~26h for all six.
REM ============================================================
cd /d "%~dp0.."

echo ==== FREEING VRAM ====
for /f "skip=1 tokens=1" %%m in ('"%LOCALAPPDATA%\AMD\AI_Bundle\Ollama\ollama.exe" ps 2^>nul') do (
  "%LOCALAPPDATA%\AMD\AI_Bundle\Ollama\ollama.exe" stop %%m 2>nul
)
taskkill /f /im llama-server.exe >nul 2>&1

echo.
echo ======== 1/6  KETH ========
venv\Scripts\python.exe -u scripts\train_character_checkpointed.py keth lora_keth_v5

echo.
echo ======== 2/6  BIA ========
venv\Scripts\python.exe -u scripts\train_character_checkpointed.py bia lora_bia_v4

echo.
echo ======== 3/6  TAZZ ========
venv\Scripts\python.exe -u scripts\train_character_checkpointed.py tazz lora_tazz_v4

echo.
echo ======== 4/6  VORSHARA ========
venv\Scripts\python.exe -u scripts\train_character_checkpointed.py vorshara lora_vorshara_v5_closeups

echo.
echo ======== 5/6  YANNAH ========
venv\Scripts\python.exe -u scripts\train_character_checkpointed.py yannah lora_yannah_v4

echo.
echo ======== 6/6  B DUBB ========
venv\Scripts\python.exe -u scripts\train_character_checkpointed.py bdubb lora_bdubb_v4

echo.
echo ==== ALL SIX FINISHED - GPU is free again ====
