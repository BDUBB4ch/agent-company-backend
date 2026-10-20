#!/bin/bash
# Voice bake-off setup (Barry OK'd 2026-09-24): VoxCPM2 (Apache-2.0), Qwen3-TTS 1.7B VoiceDesign (Apache-2.0),
# Chatterbox Turbo (MIT). Each gets its own venv under tools/tts/<name>/.venv that borrows ComfyUI's AMD ROCm torch
# (D:\ComfyUI25\venv, torch 2.9.1+rocm7.2.1) through a .pth -- torch is pinned by constraints so pip can never pull
# a CUDA/CPU wheel. Weights -> tools/tts/models/<repo>.
set -u
ROOT=/c/Users/Owner/Desktop/AgentCompanyBackend
T=$ROOT/tools/tts
BASEPY=/c/Users/Owner/AppData/Local/Programs/Python/Python312/python.exe
COMFY_SP='D:\ComfyUI25\venv\Lib\site-packages'
mkdir -p $T/models
printf 'torch==2.9.1+rocm7.2.1\ntorchaudio==2.9.1+rocm7.2.1\n' > $T/constraints.txt

mkvenv () {
  local name=$1
  [ -f $T/$name/.venv/Scripts/python.exe ] || $BASEPY -m venv $T/$name/.venv
  echo "$COMFY_SP" > $T/$name/.venv/Lib/site-packages/zz_comfy_rocm_torch.pth
  $T/$name/.venv/Scripts/python.exe -m pip install -q --upgrade pip
}

echo "== venvs $(date +%T)"
mkvenv voxcpm;     $T/voxcpm/.venv/Scripts/python.exe -m pip install -q -c $T/constraints.txt voxcpm 2>&1 | tail -3
mkvenv qwen3tts;   $T/qwen3tts/.venv/Scripts/python.exe -m pip install -q -c $T/constraints.txt qwen-tts 2>&1 | tail -3
mkvenv chatterbox
CB=$T/chatterbox/.venv/Scripts/python.exe
$CB -m pip install -q --no-deps chatterbox-tts 2>&1 | tail -3
$CB -m pip install -q -c $T/constraints.txt "numpy<2" librosa==0.11.0 s3tokenizer transformers==5.2.0 diffusers==0.29.0 \
    "resemble-perth>=1.0.0" conformer==0.3.2 safetensors==0.5.3 pyloudnorm omegaconf 2>&1 | tail -3
for n in voxcpm qwen3tts chatterbox; do
  echo "$n: $($T/$n/.venv/Scripts/python.exe -c 'import torch;print(torch.__version__, torch.cuda.is_available())' 2>&1 | tail -1)"
done

echo "== weights $(date +%T)"
HF=$ROOT/venv/Scripts/python.exe
for repo in openbmb/VoxCPM2 Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign Qwen/Qwen3-TTS-Tokenizer-12Hz ResembleAI/chatterbox-turbo; do
  $HF -c "from huggingface_hub import snapshot_download as s; print(s('$repo', local_dir=r'$(cygpath -w $T/models)\\${repo//\//__}'))" 2>&1 | tail -1
done
du -sh $T/models/* $T/*/.venv 2>/dev/null
echo "== done $(date +%T)"
