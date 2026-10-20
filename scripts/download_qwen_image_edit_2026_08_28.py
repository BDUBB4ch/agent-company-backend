"""Download Qwen-Image-Edit 2509 for ComfyUI (Barry's go, 2026-08-28).

WHY 2509 fp8_e4m3fn and not the newer 2511: 2511 ships only as fp8mixed or
int8_convrot, and fp8mixed is the format community reports flag as
friction-prone on AMD. fp8_e4m3fn is the format ALREADY PROVEN on this card
(Kontext fp8_scaled, LTX 2.3 fp8 both run). Proven format > newest version
when the question is "does it run on RDNA4 at all". Revisit 2511 once 2509
is verified working.

Why Qwen-Image-Edit at all: it replaces FLUX Kontext, which is (a) filtered
-- it silently no-op'd a nude edit, against Barry's no-filtering rule -- and
(b) non-commercial, so it can never touch B Dubb product work. Qwen is
Apache 2.0: commercial-clean for the store AND the film.

Resumable (curl -C -), verifies size after each file, never overwrites a
complete file. Files land in ComfyUI's standard folders.
"""
import os
import subprocess
import sys

COMFY = os.path.join(os.path.dirname(__file__), "..", "tools", "ComfyUI", "models")
# ⚠️ The EDIT repo carries only diffusion_models. The text encoder and VAE
# live in the BASE Qwen-Image repo and are shared across both -- pointing
# all three at the edit repo silently wrote two zero-byte files.
EDIT = "https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files"
CORE = "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files"

FILES = [
    ("diffusion_models", "qwen_image_edit_2509_fp8_e4m3fn.safetensors",
     f"{EDIT}/diffusion_models/qwen_image_edit_2509_fp8_e4m3fn.safetensors", 19.0),
    ("text_encoders", "qwen_2.5_vl_7b_fp8_scaled.safetensors",
     f"{CORE}/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors", 8.0),
    ("vae", "qwen_image_vae.safetensors",
     f"{CORE}/vae/qwen_image_vae.safetensors", 0.2),
]


def main():
    for folder, name, url, approx_gb in FILES:
        dest_dir = os.path.join(COMFY, folder)
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, name)
        if os.path.isfile(dest):
            have = os.path.getsize(dest) / (1024 ** 3)
            # within 5% of expected == already complete
            if have >= approx_gb * 0.95:
                print(f"[skip] {name} already here ({have:.1f} GB)", flush=True)
                continue
            print(f"[resume] {name} at {have:.1f} of ~{approx_gb} GB", flush=True)
        else:
            print(f"[get] {name} (~{approx_gb} GB) -> models/{folder}/", flush=True)
        r = subprocess.run(
            ["curl", "-L", "-C", "-", "--retry", "5", "--retry-delay", "5",
             "-o", dest, url],
            capture_output=True, text=True)
        if r.returncode != 0:
            print(f"[FAIL] {name}: {r.stderr[-300:]}", flush=True)
            sys.exit(1)
        got = os.path.getsize(dest) / (1024 ** 3)
        print(f"[done] {name}: {got:.2f} GB", flush=True)
        if got < approx_gb * 0.95:
            print(f"[WARN] {name} smaller than expected (~{approx_gb} GB) "
                  "-- likely truncated, re-run to resume", flush=True)
    print("\nall files present.", flush=True)


main()
