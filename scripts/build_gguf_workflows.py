"""Build GGUF variants of the LTX video workflows (2026-08-04).

Reads workflows/comfy_t2v_ltx_api.json + comfy_i2v_ltx_api.json and writes
*_gguf_api.json twins. Only the model plumbing changes:

  - node 236 CheckpointLoaderSimple (28GB fp8) is DELETED
  - node 400 UnetLoaderGGUF loads the 12.6GB UD-Q3_K_M transformer
  - node 401 VAELoader loads the standalone video VAE
  - every ["236", 2] video-VAE reference is rewired to ["401", 0]
  - node 232 (distilled LoRA @ 0.5) now feeds from 400

Nodes 221 (audio VAE) and 243 (text encoder connectors) keep reading from a
file in models/checkpoints. By default that stays the 28GB fp8 donor (mmap'd
key extraction -- RAM-cheap, zero VRAM). Pass --standalone to point them at
the small unsloth files instead, ONLY after the safetensors header check
proves the key prefixes match what the core loaders filter on.

Everything else -- sampler sigmas, upscaler, and the node IDs the backend
patches (266/247/257/258/225/260/237/325/201) -- is byte-identical.
"""
import argparse
import json
import os

ROOT = os.path.join(os.path.dirname(__file__), "..", "workflows")
# UD-Q3_K_S, not K_M: measured 2026-08-04, K_M (13.1GB) loaded fully but left
# ~350MB for activations -> 4.2GB spilled to shared memory, 207s/step. K_S
# (10.6GB) leaves ~2.9GB of true headroom on the 16GB card.
GGUF_UNET = "ltx-2.3-22b-dev-UD-Q3_K_S.gguf"
VIDEO_VAE = "ltx-2.3-22b-dev_video_vae.safetensors"
AUDIO_VAE_STANDALONE = "ltx-2.3-22b-dev_audio_vae.safetensors"
CONNECTORS_STANDALONE = "ltx-2.3-22b-dev_embeddings_connectors.safetensors"


def convert(src: str, dst: str, standalone: bool) -> None:
    with open(os.path.join(ROOT, src), encoding="utf-8") as fh:
        wf = json.load(fh)

    assert wf["236"]["class_type"] == "CheckpointLoaderSimple", src
    del wf["236"]
    wf["400"] = {"class_type": "UnetLoaderGGUF",
                 "inputs": {"unet_name": GGUF_UNET}}
    wf["401"] = {"class_type": "VAELoader",
                 "inputs": {"vae_name": VIDEO_VAE}}

    rewired = []
    for nid, node in wf.items():
        for key, val in node.get("inputs", {}).items():
            if isinstance(val, list) and val and val[0] == "236":
                if val[1] == 2:          # video VAE output
                    node["inputs"][key] = ["401", 0]
                elif val[1] == 0:        # model output (LoRA loader)
                    node["inputs"][key] = ["400", 0]
                else:
                    raise SystemExit(f"unexpected ref to 236 slot {val[1]} in node {nid}")
                rewired.append((nid, key))

    if standalone:
        wf["221"]["inputs"]["ckpt_name"] = AUDIO_VAE_STANDALONE
        wf["243"]["inputs"]["ckpt_name"] = CONNECTORS_STANDALONE

    out = os.path.join(ROOT, dst)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(wf, fh, indent=2)
    print(f"{src} -> {dst}  (rewired {rewired}, standalone={standalone})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--standalone", action="store_true",
                    help="point audio VAE + connectors at the small unsloth "
                         "files instead of the 28GB fp8 donor")
    args = ap.parse_args()
    convert("comfy_t2v_ltx_api.json", "comfy_t2v_ltx_gguf_api.json", args.standalone)
    convert("comfy_i2v_ltx_api.json", "comfy_i2v_ltx_gguf_api.json", args.standalone)
