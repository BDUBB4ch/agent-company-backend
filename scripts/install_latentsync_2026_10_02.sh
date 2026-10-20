#!/usr/bin/env bash
# LatentSync 1.5 lip-sync, AMD-only install (2026-10-02, Barry: "go ahead with the lip sync download").
# 1.6 needs 18 GB VRAM (README) -> 1.5 (8 GB). Only the two inference files are downloaded:
#   huggingface.co/ByteDance/LatentSync-1.5: latentsync_unet.pt (5.07 GB, scanned Safe), whisper/tiny.pt (75.6 MB, Safe)
# (the two "suspicious" files are in auxiliary/ -- training/eval only -- NOT downloaded).
# Torch = the same ROCm build Laya runs (copied venv, pinned by constraints); onnxruntime-gpu (NVIDIA) -> onnxruntime (CPU).
set -u
ROOT=/c/Users/Owner/Desktop/AgentCompanyBackend
LOG=$ROOT/data/latentsync_install.log
VENV=$ROOT/tools/latentsync-venv
CODE=$ROOT/tools/latentsync
PY=$VENV/Scripts/python.exe
log() { echo "$(date +%H:%M:%S) $*" | tee -a "$LOG"; }
: > "$LOG"
log "1/5 copy Laya's ROCm venv -> tools/latentsync-venv"
if [ ! -x "$PY" ]; then
  powershell -NoProfile -Command "robocopy '$(cygpath -w $ROOT/tools/laya-gpu-venv)' '$(cygpath -w $VENV)' /E /MT:16 /NFL /NDL /NJH /NJS /NP | Out-Null; exit 0"
fi
"$PY" -c "import torch;print('torch',torch.__version__,'gpu',torch.cuda.is_available())" >>"$LOG" 2>&1 || { log "FAILED: copied venv has no working torch"; exit 1; }
log "2/5 clone code"
[ -d "$CODE/.git" ] || git clone --depth 1 https://github.com/bytedance/LatentSync "$CODE" >>"$LOG" 2>&1 || { log "FAILED: git clone"; exit 1; }
log "3/5 python parts (torch pinned to ROCm)"
cat > "$CODE/constraints-amd.txt" <<'EOF'
torch==2.9.1+rocm7.2.1
torchvision==0.24.1+rocm7.2.1
EOF
"$PY" -m pip install --find-links "$ROOT/tools/ComfyUI/wheels" "$ROOT/tools/ComfyUI/wheels/torchvision-0.24.1+rocm7.2.1-cp312-cp312-win_amd64.whl" -c "$CODE/constraints-amd.txt" >>"$LOG" 2>&1 || log "warn: torchvision install"
"$PY" -m pip install --find-links "$ROOT/tools/ComfyUI/wheels" -c "$CODE/constraints-amd.txt" \
  diffusers==0.32.2 transformers==4.48.0 decord accelerate einops omegaconf opencv-python mediapipe \
  python_speech_features librosa scenedetect ffmpeg-python imageio imageio-ffmpeg lpips face-alignment \
  "huggingface-hub<1.0" kornia onnxruntime DeepCache >>"$LOG" 2>&1 || log "warn: some packages failed -- see above"
"$PY" -m pip install --find-links "$ROOT/tools/ComfyUI/wheels" -c "$CODE/constraints-amd.txt" insightface==0.7.3 >>"$LOG" 2>&1 || log "warn: insightface failed"
log "4/5 download the two inference files"
"$PY" - >>"$LOG" 2>&1 <<EOF
from huggingface_hub import hf_hub_download
for f in ("latentsync_unet.pt", "whisper/tiny.pt"):
    p = hf_hub_download("ByteDance/LatentSync-1.5", f, local_dir=r"$(cygpath -w $CODE)\\checkpoints")
    import os; print("downloaded", f, os.path.getsize(p), "bytes")
EOF
log "5/5 smoke test"
cd "$CODE" && "$PY" - >>"$LOG" 2>&1 <<'EOF'
import torch, importlib
print("torch", torch.__version__, "gpu", torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else "")
for m in ("diffusers", "transformers", "decord", "mediapipe", "insightface", "onnxruntime", "face_alignment", "kornia"):
    try:
        importlib.import_module(m); print("ok", m)
    except Exception as e:
        print("MISSING", m, type(e).__name__, e)
try:
    from latentsync.pipelines.lipsync_pipeline import LipsyncPipeline
    print("ok latentsync pipeline import")
except Exception as e:
    print("PIPELINE IMPORT FAILED", type(e).__name__, e)
EOF
log "=== install done ==="
