"""Render a character onto a POSE SKELETON via ControlNet Union ProMax.

This is the body-geometry lane. Identity comes from the LoRA (and later
IP-Adapter); PROPORTION comes from the skeleton, which is the one thing neither
of those can control -- Keth reads ~4ft only if the geometry says so.

Union model note: it is one file covering many control types, so the type must
be declared explicitly with SetUnionControlNetType ("openpose"). It was NOT
trained on hand/face keypoints, so this is bodies only.

Usage:
    python scripts/render_posed.py --pose pose_short_5heads.png --lora keth_character.safetensors \
        --prompt "@Keth, full body standing, facility jumpsuit, barefoot, plain background"
"""
import argparse
import json
import pathlib
import time
import urllib.request
import uuid

COMFY = "http://127.0.0.1:8188"
ROOT = pathlib.Path(__file__).resolve().parent.parent
CKPT = "RealVisXL_V5.0_fp16.safetensors"
CONTROLNET = "controlnet-union-promax-sdxl-1.0.safetensors"
VAE = "sdxl.vae.safetensors"


def build(pose, lora, strength, prompt, negative, seed, cn_strength, size):
    wf = {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CKPT}},
        # explicit fp16-fix VAE instead of the checkpoint's baked one
        "20": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "10": {"class_type": "LoraLoader", "inputs": {
            "lora_name": lora, "strength_model": strength, "strength_clip": strength,
            "model": ["4", 0], "clip": ["4", 1]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["10", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["10", 1]}},
        "11": {"class_type": "LoadImage", "inputs": {"image": pose}},
        "12": {"class_type": "ControlNetLoader", "inputs": {"control_net_name": CONTROLNET}},
        # union is multi-purpose -- the type has to be declared
        "13": {"class_type": "SetUnionControlNetType",
               "inputs": {"control_net": ["12", 0], "type": "openpose"}},
        "14": {"class_type": "ControlNetApplyAdvanced", "inputs": {
            "positive": ["6", 0], "negative": ["7", 0], "control_net": ["13", 0],
            "image": ["11", 0], "strength": cn_strength,
            "start_percent": 0.0, "end_percent": 0.85}},
        "5": {"class_type": "EmptyLatentImage",
              "inputs": {"width": size, "height": size, "batch_size": 1}},
        "3": {"class_type": "KSampler", "inputs": {
            "seed": seed, "steps": 25, "cfg": 6.0, "sampler_name": "dpmpp_2m",
            "scheduler": "karras", "denoise": 1.0, "model": ["10", 0],
            "positive": ["14", 0], "negative": ["14", 1], "latent_image": ["5", 0]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["20", 0]}},
        "9": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": "posed", "images": ["8", 0]}},
    }
    return wf


def run(wf, label):
    req = urllib.request.Request(
        f"{COMFY}/prompt",
        data=json.dumps({"prompt": wf, "client_id": str(uuid.uuid4())}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        pid = json.loads(urllib.request.urlopen(req, timeout=120).read())["prompt_id"]
    except urllib.error.HTTPError as e:
        print(f"{label}: SUBMIT FAILED {e.code}\n{e.read().decode()[:900]}")
        return
    t0 = time.time()
    while time.time() - t0 < 600:
        h = json.loads(urllib.request.urlopen(f"{COMFY}/history/{pid}", timeout=60).read())
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("status_str") == "error":
                print(f"{label}: FAILED {str(st.get('messages', [])[-2:])[:700]}")
                return
            outs = [i["filename"] for n in h[pid].get("outputs", {}).values()
                    for i in n.get("images", [])]
            print(f"{label}: done in {time.time()-t0:.0f}s -> {outs}")
            return
        time.sleep(3)
    print(f"{label}: TIMEOUT")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pose", required=True, help="filename in ComfyUI/input ROOT")
    ap.add_argument("--lora", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--negative", default="cartoon, anime, watermark, plastic skin, "
                                          "closed eyes, blurry, low quality, elderly")
    ap.add_argument("--strength", type=float, default=1.0)
    ap.add_argument("--cn-strength", type=float, default=0.8)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--label", default="posed")
    a = ap.parse_args()
    wf = build(a.pose, a.lora, a.strength, a.prompt, a.negative, a.seed,
               a.cn_strength, a.size)
    wf["9"]["inputs"]["filename_prefix"] = a.label
    run(wf, a.label)
