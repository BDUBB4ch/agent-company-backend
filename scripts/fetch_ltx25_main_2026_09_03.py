r"""LTX-2.5 transformer + text encoders, UNGATED sources only. -> D:\LTX25

WHY THESE REPOS, not the ones the guides name:
  elix3r/* is MANUAL-APPROVAL gated. `HfApi.model_info` returns OK for it
  (gated='auto') and the actual file download still 403s with "you are not in
  the authorized list" -- metadata access and file access are separate things
  on Hugging Face, which is a trap worth remembering. Lightricks/LTX-2.5 auto-
  granted fine (its VAEs pulled without issue); the community GGUF repos below
  are ungated outright.

TRANSFORMER: realrebelai over Abiray/vantagewithai despite being a hair larger.
  Its README documents the baked-in metadata fix: ComfyUI reads LTX-2.5's
  transformer config from a 61-key __metadata__ block that GGUF has no field
  for, so a naive conversion silently builds a 2.3-SHAPED model -- no error,
  just video with the wrong audio. Given how long silent/broken LTX audio has
  already cost this build, the repo that says it fixed that wins.

  DISTILLED, not dev, on purpose: few-step schedule at CFG 1.0. The 2026-08-04
  finding that killed LTX-2.3 GGUF on this card was that K-quant dequantises
  EVERY step, making a resident GGUF 4-6x slower than the streamed fp8. Pay
  that penalty over ~4-8 steps instead of a full schedule and the arithmetic
  changes. That is the whole bet being tested here.

ENCODERS: both are int8-convrot .safetensors, which load through stock
  ComfyUI 0.32+ comfy_quant -- no GGUF node and no gemma4 allowlist patch
  needed for the encoder path.
   - official = the baseline
   - uncensored = the reason to care. Sulphur 2 is an LTX-2.3 finetune and does
     NOT follow to 2.5, so Elliot's gore/nudity work has no uncensored DiT on
     2.5. An uncensored TEXT ENCODER is not the same thing -- it removes
     prompt-level refusal, not model-level -- but it is the closest available
     path and it costs one download to find out.
"""
import os
from huggingface_hub import hf_hub_download

ROOT = r"D:\LTX25\models"

JOBS = [
    # (repo, filename, dest_subdir, label)
    ("realrebelai/LTX-2.5_GGUFs", "LTX-2.5-Distilled-Q4_K_M.gguf",
     "unet", "transformer Q4_K_M (distilled)"),
    ("Lightricks/LTX-2.5",
     "text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors",
     "text_encoders", "official int8 encoder"),
    ("DeepNeuralNerd/Gemma-4-12B-it-uncensored-heretic-DeepNeuralNerd-LTX_2.5_ComfyUI",
     "Gemma-4-12B-it-uncensored-heretic - DeepNeuralNerd -LTX 2.5-ComfyUI-int8convrot.safetensors",
     "text_encoders", "UNCENSORED int8 encoder"),
    # smaller fallback if Q4_K_M leaves too little room for activations
    ("realrebelai/LTX-2.5_GGUFs", "LTX-2.5-Distilled-Q3_K_M.gguf",
     "unet", "transformer Q3_K_M (fallback)"),
]

REFS = [("realrebelai/LTX-2.5_GGUFs", "README.md")]

for repo, fn in REFS:
    try:
        hf_hub_download(repo_id=repo, filename=fn,
                        local_dir=os.path.join(r"D:\LTX25\ref", repo.split("/")[0]))
        print("[ref ] %s %s" % (repo, fn), flush=True)
    except Exception as e:
        print("[ref FAIL] %s: %s" % (fn, str(e)[:120]), flush=True)

for repo, fn, dest, label in JOBS:
    out = os.path.join(ROOT, dest)
    os.makedirs(out, exist_ok=True)
    target = os.path.join(out, os.path.basename(fn))
    if os.path.exists(target) and os.path.getsize(target) > 1024 ** 3:
        print("[skip] %s -- %.2f GB already on disk" % (label,
              os.path.getsize(target) / 1e9), flush=True)
        continue
    print("[get ] %s <- %s" % (label, repo), flush=True)
    try:
        p = hf_hub_download(repo_id=repo, filename=fn, local_dir=out)
        if os.path.abspath(p) != os.path.abspath(target):
            os.replace(p, target)
        print("[done] %s -- %.2f GB" % (label, os.path.getsize(target) / 1e9), flush=True)
    except Exception as e:
        print("[FAIL] %s :: %s" % (label, str(e)[:200]), flush=True)

print("ALL DONE", flush=True)
