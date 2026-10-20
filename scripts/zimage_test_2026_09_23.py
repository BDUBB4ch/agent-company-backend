"""Z-Image Turbo speed/quality test on Barry's RX 9070 XT (2026-09-23).

    ./venv/Scripts/python.exe scripts/zimage_test_2026_09_23.py

Barry: "test z image on my card". Standalone test -- not wired into the
office. Model: Comfy-Org z_image_turbo int8_convrot (6.2GB) + qwen_3_4b text
encoder + the Flux ae VAE. Template settings: 9 steps, cfg 1.0,
res_multistep / simple, AuraFlow shift 3.

Owns the render flag (token) so no office chat evicts ComfyUI mid-test, and
clears only its own flag. Results -> data/zimage_test_2026-09-23.json.
"""
import asyncio
import json
import os
import sys
import time
import urllib.request
import uuid

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))

import comfy_image  # noqa: E402
import llm_router  # noqa: E402
from config import COMFY_DIR  # noqa: E402

COMFY = "http://127.0.0.1:8188"
RENDER_FLAG = os.path.join(ROOT, "data", "video_rendering.flag")
OUT_JSON = os.path.join(ROOT, "data", "zimage_test_2026-09-23.json")
TOKEN = f"zimage-test-{time.time()}"

TESTS = [
    ("herbs_hands", 1024, 1024,
     "Photograph of a woman in her forties with long dark braided hair, standing at a "
     "worn wooden kitchen counter, both hands holding a white ceramic teacup with steam "
     "rising, dried chamomile and lavender bundles hanging behind her, glass jars of "
     "loose tea on a shelf, soft window light from the left, natural skin texture, "
     "shallow depth of field, 50mm lens"),
    ("scarecrow_night", 1024, 1024,
     "Photograph of a tattered scarecrow on a wooden post in a dead cornfield at night, "
     "burlap sack face with stitched mouth, straw poking out of a torn flannel shirt, "
     "full moon behind thin clouds, fog low over the ground, a farmhouse far away with "
     "one lit window, cold blue moonlight, film grain, horror atmosphere"),
    ("vertical_fullbody", 832, 1472,
     "Full body photograph of an old man in a flannel shirt, denim overalls and muddy "
     "boots, standing on a gravel farm road at golden hour, holding a lantern in his "
     "right hand, a red barn behind him, long shadows, his whole figure visible from "
     "boots to hat"),
    # Text-only accuracy tests (Barry: "yes add both"). Z-Image takes no
    # reference picture, so these show how well it follows a description,
    # NOT identity. Wording from her canon / her own words; weight syntax and
    # retired-era details dropped because the engine does not read them.
    ("vorshara_text", 1024, 1024,
     "Photograph of Lady Vor'Shara Vel, an alien noblewoman with a balanced curvy "
     "elegant body and smooth greyish-white skin. Her face has four electric-blue eyes "
     "arranged as two pairs stacked vertically, each with a dark vertical slit pupil, "
     "a small nose, full lips, and alien dot markings on her cheeks. She has no hair: "
     "long organic tendrils fall from her head, decorated with gold rings, purple "
     "gemstones and emerald inlays. Gold nose ring with a gem-studded chain to her ear, "
     "gold and diamond necklace with a glowing unknown gem. She wears a fully sheer "
     "pale-purple couture gown of translucent see-through fabric, revealing her areolas "
     "and breast skin tone beneath and pubic hair, with gold filigree, alien glyph "
     "embroidery and gold detailing contouring her body. She stands in an interior "
     "garden atrium with a reflecting pool, dark green marble columns with gold bands "
     "and living vines, warm golden light"),
    ("amara_text", 1024, 1024,
     "Photograph of a woman in her thirties with olive skin, faint freckles across her "
     "nose and cheeks, thick unruly eyebrows trimmed into a sharp arch, and "
     "shoulder-length asymmetric layered hair, espresso brown fading to coppery "
     "chestnut at the ends. Her body is athletic but soft, with a narrow waist opening "
     "into wide hips, a full chest and a full round backside. She wears a loose white "
     "linen shirt with the sleeves rolled up and paint smudges on her fingers, holding "
     "a paintbrush in her right hand in front of a large unfinished canvas in a sunlit "
     "loft studio, jars of brushes on a paint-spattered table, natural skin texture"),
]


def _flag(on):
    try:
        if on:
            open(RENDER_FLAG, "w").write(TOKEN)
        elif open(RENDER_FLAG).read().strip() == TOKEN:
            os.remove(RENDER_FLAG)
    except OSError:
        pass


def _get(path):
    return json.loads(urllib.request.urlopen(COMFY + path, timeout=60).read())


def clip_type():
    info = _get("/object_info/CLIPLoader")
    types = info["CLIPLoader"]["input"]["required"]["type"][0]
    for t in ("z_image", "lumina2", "qwen_image"):
        if t in types:
            return t
    raise SystemExit(f"no Z-Image clip type in {types}")


def graph(prompt, w, h, seed, prefix, ctype):
    return {
        "1": {"class_type": "UNETLoader", "inputs": {
            "unet_name": "z_image_turbo_int8_convrot.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3.0}},
        "3": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": "qwen_3_4b.safetensors", "type": ctype}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": prompt}},
        "6": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["5", 0]}},
        "7": {"class_type": "EmptySD3LatentImage", "inputs": {
            "width": w, "height": h, "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {
            "model": ["2", 0], "positive": ["5", 0], "negative": ["6", 0],
            "latent_image": ["7", 0], "seed": seed, "steps": 9, "cfg": 1.0,
            "sampler_name": "res_multistep", "scheduler": "simple", "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["4", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": prefix}},
    }


def run_one(wf, timeout=1800):
    req = urllib.request.Request(
        COMFY + "/prompt",
        data=json.dumps({"prompt": wf, "client_id": str(uuid.uuid4())}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        pid = json.loads(urllib.request.urlopen(req, timeout=120).read())["prompt_id"]
    except urllib.error.HTTPError as e:
        raise SystemExit("rejected:\n" + e.read().decode()[:1500])
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(2)
        hist = _get(f"/history/{pid}")
        if pid not in hist:
            continue
        st = hist[pid].get("status", {})
        if st.get("status_str") == "error":
            raise SystemExit("failed: " + json.dumps(st.get("messages", []))[:1500])
        for out in hist[pid].get("outputs", {}).values():
            for img in out.get("images", []):
                return time.time() - t0, os.path.join(COMFY_DIR, "output", img["filename"])
    raise SystemExit("timed out")


async def main():
    if comfy_image.render_in_progress():
        raise SystemExit("a render is already running -- not starting")
    _flag(True)
    results = []
    try:
        await llm_router.unload_all_models()
        if not await comfy_image.ensure_running(timeout_s=600, mode="image"):
            raise SystemExit("ComfyUI did not start")
        ctype = clip_type()
        print("clip type:", ctype, flush=True)
        for i, (name, w, h, prompt) in enumerate(TESTS):
            secs, path = run_one(graph(prompt, w, h, 1234 + i, f"zimage_test_{name}", ctype))
            print(f"{name}: {w}x{h} {secs:.1f}s -> {path}", flush=True)
            results.append({"name": name, "size": f"{w}x{h}", "seconds": round(secs, 1),
                            "file": path, "first_run_includes_load": i == 0})
        # warm repeat of test 1 = the real per-picture time
        name, w, h, prompt = TESTS[0]
        secs, path = run_one(graph(prompt, w, h, 999, "zimage_test_warm", ctype))
        print(f"warm repeat: {secs:.1f}s -> {path}", flush=True)
        results.append({"name": "warm_repeat", "size": f"{w}x{h}", "seconds": round(secs, 1),
                        "file": path})
    finally:
        _flag(False)
        json.dump(results, open(OUT_JSON, "w"), indent=2)


if __name__ == "__main__":
    asyncio.run(main())
