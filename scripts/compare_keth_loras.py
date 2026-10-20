"""Render the SAME prompt and seed with no LoRA, with v5, and with v7, so the
question "did v7 actually learn anything" has an answer instead of a guess.

This is the test written into data/HANDOFF_2026-08-08.md: if the v7 render is
indistinguishable from the no-LoRA control, the LoRA is NOT learning and the
next step is diagnosis, not another 4-hour retrain.

Method, copied from compare_vorshara_loras.py because it is the one that
produced a usable answer:
  - the LoraLoader is wired EXPLICITLY here rather than going through
    comfy_image's @mention injection, which would chain whatever
    keth_character.safetensors currently is and defeat the comparison.
  - the control render is regenerated NOW at the same seed and prompt rather
    than reusing the older ctrl_nolora_00001_.png, whose prompt and seed are
    not recorded. Comparing against an unknown baseline proves nothing.
  - the prompt is TRIGGER-LED and phrased like the training captions
    (`@Keth, close-up portrait, ...`), i.e. in-distribution. Canon words are
    deliberately NOT stacked into it: the whole point is to see what the
    weights hold on their own. Spec-in-prompt is how a bare human render gets
    mistaken for a working LoRA.
  - "deformed" is NOT in the negative -- it suppresses anatomically unusual
    features, which on an alien with a 4-foot frame and an elongated cranium
    would fight the very thing being tested.

Run (GPU must be free):
    venv/Scripts/python.exe scripts/compare_keth_loras.py
"""
import json
import pathlib
import time
import urllib.request
import uuid

COMFY = "http://127.0.0.1:8188"
ROOT = pathlib.Path(__file__).resolve().parent.parent

# The handoff's test prompt, verbatim.
POSITIVE = "@Keth, close-up portrait, gray facility jumpsuit"
NEGATIVE = "cartoon, anime, watermark, blurry, low quality, text"
SEED = 42
STRENGTH = 1.0
WIDTH, HEIGHT = 1024, 1024

RUNS = [
    ("keth_ctrl_nolora", None),
    ("keth_cmp_v5", "keth_character_v5.safetensors"),
    ("keth_cmp_v7", "keth_character_v7.safetensors"),
]


def build(lora_name, prefix, strength=None):
    wf = json.loads((ROOT / "workflows" / "comfy_t2i_sdxl_api.json").read_text(encoding="utf-8"))
    if lora_name:
        wf["10"] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": lora_name,
                "strength_model": strength or STRENGTH,
                "strength_clip": strength or STRENGTH,
                "model": ["4", 0],
                "clip": ["4", 1],
            },
        }
        model_src, clip_src = ["10", 0], ["10", 1]
    else:
        model_src, clip_src = ["4", 0], ["4", 1]

    wf["3"]["inputs"]["model"] = model_src
    wf["3"]["inputs"]["seed"] = SEED
    wf["6"]["inputs"] = {"text": POSITIVE, "clip": clip_src}
    wf["7"]["inputs"] = {"text": NEGATIVE, "clip": clip_src}
    wf["5"]["inputs"]["width"] = WIDTH
    wf["5"]["inputs"]["height"] = HEIGHT
    wf["9"]["inputs"]["filename_prefix"] = prefix
    return wf


def run(prefix, lora_name, strength=None):
    wf = build(lora_name, prefix, strength)
    req = urllib.request.Request(
        f"{COMFY}/prompt",
        data=json.dumps({"prompt": wf, "client_id": str(uuid.uuid4())}).encode(),
        headers={"Content-Type": "application/json"},
    )
    pid = json.loads(urllib.request.urlopen(req, timeout=120).read())["prompt_id"]
    print(f"{prefix:<18} queued {pid}  ({lora_name or 'NO LORA'})", flush=True)
    t0 = time.time()
    while time.time() - t0 < 900:
        hist = json.loads(urllib.request.urlopen(f"{COMFY}/history/{pid}", timeout=60).read())
        if pid in hist:
            st = hist[pid].get("status", {})
            if st.get("status_str") == "error":
                print(f"   FAILED: {str(st.get('messages', [])[-3:])[:600]}", flush=True)
                return
            outs = [i["filename"] for n in hist[pid].get("outputs", {}).values()
                    for i in n.get("images", [])]
            print(f"   done in {time.time()-t0:.0f}s -> {outs}", flush=True)
            return
        time.sleep(3)
    print("   TIMEOUT", flush=True)


if __name__ == "__main__":
    print(f"prompt : {POSITIVE}")
    print(f"seed   : {SEED}   strength: {STRENGTH}   {WIDTH}x{HEIGHT}\n")
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--sweep-v7":
        # Is v7 CORRUPT, or just too strong? A corrupt LoRA fries at any
        # weight; an over-strong one cleans up as the weight drops.
        for w in (0.8, 0.6, 0.4):
            run(f"keth_v7_w{int(w*10)}", "keth_character_v7.safetensors", w)
    else:
        for prefix, lora in RUNS:
            run(prefix, lora)
