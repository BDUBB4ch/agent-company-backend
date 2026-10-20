"""Solo test render for each freshly-trained _v2 character LoRA (2026-08-05).

Mirrors production exactly -- same t2i workflow, LoraLoader chained off the
checkpoint at solo strength 0.9, @Name trigger in the prompt -- but loads the
_v2 file explicitly, because the live @mention map still points at v1 until
Barry approves each character. Fixed seed so re-runs compare cleanly.
"""
import json
import os
import time
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
WF_PATH = os.path.join(ROOT, "workflows", "comfy_t2i_sdxl_api.json")
HOST = "http://127.0.0.1:8188"

TESTS = {
    "bdubb": "@BDUBB portrait, black baseball cap with a black star, black hoodie "
             "under tactical vest, gold number 4 chain, studio lighting, photo",
    "bia":   "@Bia close-up portrait, sleek faded pixie cut, detailed eyes and lips, "
             "studio lighting, photo",
    "yannah": "@Yannah close-up portrait, gold freckle spots on her face, hazel "
              "green-brown eyes, studio lighting, photo",
    "keth":  "@Keth portrait, gray skin, elongated hairless cranium, green irises "
             "with dark pupils and no whites, gray facility jumpsuit, photo",
    "tazz":  "@Tazz portrait, muscular build, two long dark braids, jungle "
             "background, photo",
}
NEGATIVE = "cartoon, anime, watermark, blurry, low quality, multiple people, collage, grid"


def api(path, payload=None, timeout=30):
    req = urllib.request.Request(
        HOST + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def main():
    queued = {}
    for name, prompt in TESTS.items():
        with open(WF_PATH, encoding="utf-8") as fh:
            wf = json.load(fh)
        wf["90"] = {"class_type": "LoraLoader", "inputs": {
            "model": ["4", 0], "clip": ["4", 1],
            "lora_name": f"{name}_character_v2.safetensors",
            "strength_model": 0.9, "strength_clip": 0.9}}
        for nid, node in wf.items():
            if nid == "90":
                continue
            for k, v in list(node.get("inputs", {}).items()):
                if isinstance(v, list) and len(v) == 2 and v[0] == "4" and v[1] in (0, 1):
                    node["inputs"][k] = ["90", v[1]]
        wf["6"]["inputs"]["text"] = prompt
        wf["7"]["inputs"]["text"] = NEGATIVE
        wf["3"]["inputs"]["seed"] = 42
        wf["9"]["inputs"]["filename_prefix"] = f"v2test_{name}"
        queued[name] = api("/prompt", {"prompt": wf}, timeout=60)["prompt_id"]
        print(f"queued {name}: {queued[name]}")

    deadline = time.monotonic() + 900
    done = {}
    while len(done) < len(queued) and time.monotonic() < deadline:
        time.sleep(5)
        for name, pid in queued.items():
            if name in done:
                continue
            try:
                hist = api(f"/history/{pid}")
            except Exception:
                continue
            if pid in hist:
                entry = hist[pid]
                ok = entry.get("status", {}).get("status_str")
                files = [img["filename"]
                         for out in entry.get("outputs", {}).values()
                         for img in out.get("images", [])]
                done[name] = (ok, files)
                print(f"{name}: {ok} -> {files}")
    for name in queued:
        if name not in done:
            print(f"{name}: TIMED OUT")


if __name__ == "__main__":
    main()
