"""Official int8-convrot distilled transformer -- the format ComfyUI's own
LTX-2.5 template defaults to, and the one with native HIP kernels on 0.34.

Why this and not just the GGUF we already have: the 2026-08-04 result that
killed LTX-2.3 GGUF on this card was K-quant dequantising EVERY step. int8
convrot does not do that, and `comfy_kitchen backend hip` reports
int8_linear / dequantize_int8_convrot_weight_dtype as available on gfx1201.
At 21.5GB it streams the same way the working 27GB LTX-2.3 fp8 does.
"""
import os
from huggingface_hub import hf_hub_download

OUT = r"D:\LTX25\models\unet"
FN = "diffusion_models/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors"
os.makedirs(OUT, exist_ok=True)
target = os.path.join(OUT, os.path.basename(FN))
if os.path.exists(target) and os.path.getsize(target) > 1024**3:
    print("[skip] already have %.2f GB" % (os.path.getsize(target)/1e9))
else:
    print("[get ] int8-convrot distilled transformer (21.5 GB)", flush=True)
    p = hf_hub_download(repo_id="Lightricks/LTX-2.5", filename=FN, local_dir=OUT)
    if os.path.abspath(p) != os.path.abspath(target):
        os.replace(p, target)
    print("[done] %.2f GB" % (os.path.getsize(target)/1e9))
print("ALL DONE", flush=True)
