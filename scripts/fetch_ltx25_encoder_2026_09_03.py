"""The 9.51GB GGUF text encoder -- the piece that unblocks LTX-2.5 on 16GB.

The 12B int8 encoder is 14.3GB and fills the card by itself: run 1 OOM'd during
text encode without ever reaching the DiT, and the only thing that got a clip out
was PYTORCH_NO_HIP_MEMORY_CACHING=1, which costs ~2x. At 9.51GB this one fits with
headroom, encodes on GPU, unloads, and hands the whole card to the video model.

Also grabs the repo's own ComfyUI-GGUF patch: unlike `ltxv` (already in
IMG_ARCH_LIST), the `gemma4` architecture is NOT in the allowlist, so the GGUF
encoder is refused without it.
"""
import os
from huggingface_hub import hf_hub_download

REPO = "elix3r/gemma4-12b-with-proj-ltx-2.5-GGUF"
ENC_OUT = r"D:\LTX25\models\text_encoders"
REF_OUT = r"D:\LTX25\ref\elix3r"
os.makedirs(ENC_OUT, exist_ok=True)

FN = "gemma4-12b-with-proj-ltx-2.5-Q5_K_M.gguf"
target = os.path.join(ENC_OUT, FN)
if os.path.exists(target) and os.path.getsize(target) > 1024**3:
    print("[skip] encoder already here, %.2f GB" % (os.path.getsize(target)/1e9))
else:
    print("[get ] %s (9.51 GB)" % FN, flush=True)
    p = hf_hub_download(repo_id=REPO, filename=FN, local_dir=ENC_OUT)
    if os.path.abspath(p) != os.path.abspath(target):
        os.replace(p, target)
    print("[done] %.2f GB" % (os.path.getsize(target)/1e9))

for f in ["patches/ComfyUI-GGUF-ltx25-gemma4.patch",
          "examples/ltx25-gguf-local-smoke.json",
          "examples/ltx25-gguf-local-two-stage-hq.json",
          "README.md", "SHA256SUMS"]:
    try:
        hf_hub_download(repo_id=REPO, filename=f, local_dir=REF_OUT)
        print("[ref ] %s" % f, flush=True)
    except Exception as e:
        print("[ref FAIL] %s: %s" % (f, str(e)[:110]), flush=True)
print("ALL DONE", flush=True)
