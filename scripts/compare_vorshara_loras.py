"""Render the SAME prompt/seed through each Vor'Shara LoRA so they can be compared.

Deliberately does NOT go through comfy_image's @mention injection -- that chains
whatever `vorshara_character.safetensors` currently is (v1), which is the opposite
of what a comparison needs. The LoraLoader is wired explicitly here.

Prompt notes:
  - trigger-led and phrased like the close-up training captions (in-distribution).
  - the eye count is NOT mentioned in the positive; the whole point is to see what
    the weights hold on their own.
  - "deformed" is REMOVED from the negative -- it actively suppresses anatomically
    unusual features, i.e. it would fight her four eyes and rig the test.
"""
import json
import pathlib
import time
import urllib.request
import uuid

COMFY = "http://127.0.0.1:8188"
ROOT = pathlib.Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# LOCKED RECIPE -- approved by Barry 2026-08-04 ("this is good"), output
# ageup1_00001_.png. Do not "improve" the wording; every descriptive addition
# tested worse. Longer prompts drove her either too young/plastic or fully
# human. His call, confirmed by the ladder: "youre prompting too much."
#
#   lora      vorshara_character_v3.safetensors
#   strength  1.0 model + clip          (NOT the 0.9 comfy_image hardcodes)
#   sampler   dpmpp_2m / karras, 25 steps, cfg 6.0, 1024x1024
#
# The age words are load-bearing and the amount is exact:
#   none                     -> too old (his first note)
#   "elderly"                -> approved (ageup1)
#   "elderly, (deep wrinkles:0.5)" -> APPROVED, final. The blend he chose.
#   "elderly, deep wrinkles" -> one notch too young (age_a)
#   heavier still            -> young porcelain doll, then a human woman
#
# MEASURED 2026-08-04: the :0.25/:0.5/:0.75 weights differ from each other by
# only 0.56-1.23 mean pixel levels, while adding the term at all moves 18.
# So this weight is a SWITCH, not a dial -- do not waste renders tuning it.
# ---------------------------------------------------------------------------
POSITIVE = ("@Vorshara, close-up portrait, head and shoulders, "
            "soft studio lighting, plain pale background, sharp focus")
NEGATIVE = ("cartoon, anime, watermark, plastic skin, closed eyes, blurry, "
            "low quality, elderly, (deep wrinkles:0.5)")
SEED = 42
STRENGTH = 1.0
WIDTH, HEIGHT = 1024, 1024

RUNS = [
    ("cmp_v1", "vorshara_character.safetensors"),
    ("cmp_v3", "vorshara_character_v3.safetensors"),
]


def build(lora_name, prefix):
    wf = json.loads((ROOT / "workflows" / "comfy_t2i_sdxl_api.json")
                    .read_text(encoding="utf-8"))
    wf["10"] = {
        "class_type": "LoraLoader",
        "inputs": {
            "lora_name": lora_name,
            "strength_model": STRENGTH,
            "strength_clip": STRENGTH,
            "model": ["4", 0],
            "clip": ["4", 1],
        },
    }
    wf["3"]["inputs"]["model"] = ["10", 0]
    wf["3"]["inputs"]["seed"] = SEED
    wf["6"]["inputs"] = {"text": POSITIVE, "clip": ["10", 1]}
    wf["7"]["inputs"] = {"text": NEGATIVE, "clip": ["10", 1]}
    wf["5"]["inputs"]["width"] = WIDTH
    wf["5"]["inputs"]["height"] = HEIGHT
    wf["9"]["inputs"]["filename_prefix"] = prefix
    return wf


def run(prefix, lora_name):
    wf = build(lora_name, prefix)
    req = urllib.request.Request(
        f"{COMFY}/prompt",
        data=json.dumps({"prompt": wf, "client_id": str(uuid.uuid4())}).encode(),
        headers={"Content-Type": "application/json"},
    )
    pid = json.loads(urllib.request.urlopen(req, timeout=120).read())["prompt_id"]
    print(f"{prefix:<8} queued {pid}  ({lora_name})")
    t0 = time.time()
    while time.time() - t0 < 600:
        hist = json.loads(urllib.request.urlopen(f"{COMFY}/history/{pid}", timeout=60).read())
        if pid in hist:
            st = hist[pid].get("status", {})
            if st.get("status_str") == "error":
                print(f"   FAILED: {str(st.get('messages', [])[-3:])[:600]}")
                return
            outs = [i["filename"] for n in hist[pid].get("outputs", {}).values()
                    for i in n.get("images", [])]
            print(f"   done in {time.time()-t0:.0f}s -> {outs}")
            return
        time.sleep(3)
    print("   TIMEOUT")


if __name__ == "__main__":
    for prefix, lora in RUNS:
        run(prefix, lora)
