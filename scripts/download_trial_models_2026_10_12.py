"""Download the two trial models (Barry 2026-10-12: 'let Ilnora finish, then try them out'). Disk + network only, no GPU.
Resumable. Files go to models/candidates/. Log: models/candidates/dl_trial_2026-10-12.log"""
import os, sys, time
from huggingface_hub import hf_hub_download
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "models", "candidates")
JOBS = [("llmfan46/Qwen3.6-35B-A3B-uncensored-heretic-Native-MTP-Preserved-GGUF",
         "Qwen3.6-35B-A3B-uncensored-heretic-Native-MTP-Preserved-Q5_K_M.gguf"),
        ("mradermacher/Huihui-GLM-4.7-Flash-abliterated-i1-GGUF", sys.argv[1] if len(sys.argv) > 1 else "")]
for repo, fn in JOBS:
    if not fn:
        continue
    t = time.time()
    p = hf_hub_download(repo_id=repo, filename=fn, local_dir=DEST)
    print(f"done {fn} {os.path.getsize(p)/1e9:.1f} GB in {time.time()-t:.0f}s", flush=True)
