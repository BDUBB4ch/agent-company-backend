"""Make Qwen-Image-Edit actually usable on a 16GB card (Barry, 2026-08-28).

MEASURED PROBLEM: the fp8 build is 19GB against ~12.9GB usable VRAM.
ComfyUI's own log said it -- "12738 MB loaded, 6745 MB offloaded" -- and a
single 20-step edit took ~20 minutes at ~57s/step because two thirds of the
model was being streamed from system RAM.

TWO FIXES, both needed:
  1. Q4_K_S GGUF at 12.2 GB -- FITS in the 12.9GB usable, so nothing spills.
     Deliberately NOT Q4_K_M (13.1GB): that is over the measured line, and
     "nearly fits" is what causes the spill in the first place.
  2. The Edit-2509 Lightning LoRA, 8-step -- cuts 20 steps to 8. The 8-step
     is chosen over the 4-step because the extra steps measurably hold
     quality. bf16 (850MB) not fp32 (1.7GB): same weights, half the file.

GGUF goes in models/unet/ and needs ComfyUI-GGUF's UnetLoaderGGUF node
(already installed here) instead of the stock UNETLoader.
"""
import os
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
COMFY = os.path.join(ROOT, "tools", "ComfyUI", "models")

FILES = [
    # ⚠️ hyphens, not underscores -- verified against the HF API file list.
    # A wrong name here does not 404 loudly; curl writes a 15-byte error
    # body and the size assert is what catches it.
    ("unet", "Qwen-Image-Edit-2509-Q4_K_S.gguf",
     "https://huggingface.co/QuantStack/Qwen-Image-Edit-2509-GGUF/resolve/main/"
     "Qwen-Image-Edit-2509-Q4_K_S.gguf", 11.4),
    ("loras", "Qwen-Image-Edit-2509-Lightning-8steps-V1.0-bf16.safetensors",
     "https://huggingface.co/lightx2v/Qwen-Image-Lightning/resolve/main/"
     "Qwen-Image-Edit-2509/Qwen-Image-Edit-2509-Lightning-8steps-V1.0-bf16.safetensors",
     0.79),
]


def main():
    for folder, name, url, approx_gib in FILES:
        dest_dir = os.path.join(COMFY, folder)
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, name)
        if os.path.isfile(dest) and os.path.getsize(dest) / (1024 ** 3) >= approx_gib * 0.95:
            print(f"[skip] {name} already complete", flush=True)
            continue
        print(f"[get] {name} (~{approx_gib} GiB) -> models/{folder}/", flush=True)
        r = subprocess.run(
            ["curl", "-L", "-C", "-", "--retry", "5", "--retry-delay", "5",
             "-o", dest, url], capture_output=True, text=True)
        got = os.path.getsize(dest) / (1024 ** 3) if os.path.isfile(dest) else 0
        if r.returncode != 0 or got < approx_gib * 0.95:
            print(f"[FAIL] {name}: {got:.2f} GiB. {r.stderr[-300:]}", flush=True)
            sys.exit(1)
        print(f"[done] {name}: {got:.2f} GiB", flush=True)
    print("\nboth files present.", flush=True)


main()
