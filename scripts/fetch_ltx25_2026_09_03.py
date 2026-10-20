r"""Fetch the LTX-2.5 16GB path to D:\LTX25. Idempotent -- re-run to resume.

Everything lands on D: deliberately. C: has ~45GB free and the working
ComfyUI install lives there; a 30GB pull onto C: would put the machine near
full while the office is running.
"""
import os, sys
from huggingface_hub import hf_hub_download

ROOT = r"D:\LTX25\models"
REF = r"D:\LTX25\ref"

JOBS = [
    # (repo, filename, dest_subdir)
    ("elix3r/LTX-2.5-22b-distilled-GGUF",
     "ltx-2.5-22b-distilled-transformer-Q5_K_M.gguf", "unet"),
    ("elix3r/gemma4-12b-with-proj-ltx-2.5-GGUF",
     "gemma4-12b-with-proj-ltx-2.5-Q5_K_M.gguf", "text_encoders"),
    # conv VAE = the low-VRAM video decoder the 16GB author recommends
    ("Lightricks/LTX-2.5", "vae/ltx-2.5-video-vae-conv-bf16.safetensors", "vae"),
    # AUDIO VAE -- missing this is the #1 cause of a silent render
    ("Lightricks/LTX-2.5", "vae/ltx-2.5-audio-vae-bf16.safetensors", "vae"),
    ("Lightricks/LTX-2.5",
     "latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors",
     "latent_upscale_models"),
    ("Lightricks/LTX-2.5",
     "latent_upscale_models/ltx-2.5-latent-temporal-upscaler-x2-bf16-1.0.safetensors",
     "latent_upscale_models"),
    ("Lightricks/LTX-2.5", "model_patches/ltx-2.5-duration-head-bf16.safetensors",
     "model_patches"),
]

# the patch + example workflows + checksums -- small, and the patch is required
REFS = [
    ("elix3r/LTX-2.5-22b-distilled-GGUF", "patches/ComfyUI-GGUF-ltx25-gemma4.patch"),
    ("elix3r/LTX-2.5-22b-distilled-GGUF", "examples/ltx25-gguf-local-smoke.json"),
    ("elix3r/LTX-2.5-22b-distilled-GGUF", "examples/ltx25-gguf-local-two-stage-hq.json"),
    ("elix3r/LTX-2.5-22b-distilled-GGUF", "SHA256SUMS"),
    ("elix3r/LTX-2.5-22b-distilled-GGUF", "README.md"),
    ("elix3r/LTX-2.5-22b-distilled-GGUF", "QUANTIZATION.md"),
    ("elix3r/gemma4-12b-with-proj-ltx-2.5-GGUF", "SHA256SUMS"),
    ("elix3r/gemma4-12b-with-proj-ltx-2.5-GGUF", "README.md"),
]

def get(repo, fn, dest):
    out = os.path.join(ROOT, dest)
    os.makedirs(out, exist_ok=True)
    target = os.path.join(out, os.path.basename(fn))
    if os.path.exists(target) and os.path.getsize(target) > 1024:
        print("[skip] %s (%.2f GB already there)" % (os.path.basename(fn),
              os.path.getsize(target)/1e9), flush=True)
        return
    print("[get ] %s <- %s" % (os.path.basename(fn), repo), flush=True)
    p = hf_hub_download(repo_id=repo, filename=fn, local_dir=out)
    # hf keeps the repo subdir structure; flatten so ComfyUI sees it
    if os.path.abspath(p) != os.path.abspath(target):
        os.replace(p, target)
    print("[done] %s (%.2f GB)" % (os.path.basename(fn),
          os.path.getsize(target)/1e9), flush=True)

for repo, fn in REFS:
    try:
        p = hf_hub_download(repo_id=repo, filename=fn, local_dir=REF)
        print("[ref ] %s" % fn, flush=True)
    except Exception as e:
        print("[ref FAIL] %s: %s" % (fn, e), flush=True)

for repo, fn, dest in JOBS:
    try:
        get(repo, fn, dest)
    except Exception as e:
        print("[FAIL] %s :: %s: %s" % (repo, fn, e), flush=True)

print("ALL DONE", flush=True)
