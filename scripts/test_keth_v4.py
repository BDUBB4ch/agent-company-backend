"""Render Keth v4 against canon so Barry can judge it.

Method borrowed from compare_vorshara_loras.py: explicit LoraLoader (NOT
comfy_image's @mention injection, which would chain whatever
keth_character.safetensors currently is), trigger-led prompts phrased like the
training captions so we stay in-distribution.

WHAT THIS TEST IS FOR -- the traits that were WRONG before:
  EARS  canon = small, low-profile, subtly pointed. The Aug-6 close-ups showed
        LARGE FLARED ears and every old caption said "small low-profile"
        regardless, teaching the phrase onto the wrong shape.
  EYES  canon = vivid green iris, dark pupil, NO sclera, NO whites.
  FEET  canon = barefoot.
  SIZE  canon = approximately four feet tall.
  SKIN  canon = textured/lined but "dignified not monstrous".

DELIBERATELY NOT NAMED IN THE POSITIVE PROMPT: ears, eyes, sclera, height.
The whole point is to see what the weights hold on their own. Naming them
would rig the test -- the same reasoning that removed "deformed" from the
Vor'Shara negative so it could not suppress her four eyes.

"deformed"/"mutated" are likewise NOT in the negative here: Keth is a
non-human skull shape and those terms fight it.
"""
import json
import pathlib
import time
import urllib.request
import uuid

COMFY = "http://127.0.0.1:8188"
ROOT = pathlib.Path(__file__).resolve().parent.parent

LORA = "keth_character_v4.safetensors"
STRENGTH = 1.0
SEED = 42
NEGATIVE = ("cartoon, anime, watermark, plastic skin, closed eyes, blurry, "
            "low quality, text, signature")

# Phrased like the v4 captions, minus every trait under test.
SHOTS = [
    ("kethv4_portrait",
     "@Keth, alien being, close-up portrait, head and shoulders, gray facility "
     "jumpsuit, plain studio background, soft lighting, sharp focus",
     1024, 1024),
    ("kethv4_fullbody",
     "@Keth, alien being, full body, standing, gray facility jumpsuit, plain "
     "studio background, soft lighting, sharp focus",
     832, 1216),
    ("kethv4_scene",
     "@Keth, alien being, sitting on the floor of a steel detention room, "
     "gray facility jumpsuit, cinematic still",
     1024, 1024),
]


def build(prefix, positive, w, h):
    wf = json.loads((ROOT / "workflows" / "comfy_t2i_sdxl_api.json")
                    .read_text(encoding="utf-8"))
    wf["10"] = {"class_type": "LoraLoader",
                "inputs": {"lora_name": LORA,
                           "strength_model": STRENGTH,
                           "strength_clip": STRENGTH,
                           "model": ["4", 0], "clip": ["4", 1]}}
    wf["3"]["inputs"]["model"] = ["10", 0]
    wf["3"]["inputs"]["seed"] = SEED
    wf["6"]["inputs"] = {"text": positive, "clip": ["10", 1]}
    wf["7"]["inputs"] = {"text": NEGATIVE, "clip": ["10", 1]}
    wf["5"]["inputs"]["width"] = w
    wf["5"]["inputs"]["height"] = h
    wf["9"]["inputs"]["filename_prefix"] = prefix
    return wf


def run(prefix, positive, w, h):
    wf = build(prefix, positive, w, h)
    req = urllib.request.Request(
        f"{COMFY}/prompt",
        data=json.dumps({"prompt": wf, "client_id": str(uuid.uuid4())}).encode(),
        headers={"Content-Type": "application/json"})
    pid = json.loads(urllib.request.urlopen(req, timeout=120).read())["prompt_id"]
    print(f"{prefix:<18} queued {pid}")
    t0 = time.time()
    while time.time() - t0 < 600:
        hist = json.loads(urllib.request.urlopen(f"{COMFY}/history/{pid}", timeout=60).read())
        if pid in hist:
            st = hist[pid].get("status", {})
            if st.get("status_str") == "error":
                print(f"   FAILED: {str(st.get('messages', [])[-3:])[:500]}")
                return
            outs = [i["filename"] for n in hist[pid].get("outputs", {}).values()
                    for i in n.get("images", [])]
            print(f"   done in {time.time()-t0:.0f}s -> {outs}")
            return
        time.sleep(3)
    print("   TIMEOUT")


if __name__ == "__main__":
    for prefix, pos, w, h in SHOTS:
        run(prefix, pos, w, h)
