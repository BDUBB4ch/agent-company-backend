"""Generate homepage hero candidates for bdubbgrowsllc.com.

Three different directions, all landscape 1344x768 (native, no upscaling -- the
current live hero is a 752px portrait stretched across a 1300px band).

Deliberately NO product bottles in frame: SDXL cannot render text, and the
existing hero proves it -- its "BIONOVA" labels are invented mush and the
packaging is wrong. Real bottles get composited later from the 1050x1050
studio shots already in the media library.

Commercial checkpoint only (RealVisXL_V5.0_fp16) -- this is B Dubb Grows
marketing, not film work, so Kontext/FLUX is off-limits.

Run:  ../venv/Scripts/python.exe scripts/generate_hero_options.py
"""
import asyncio
import json
import os
import sys
import time

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import comfy_image  # noqa: E402
from config import COMFY_HOST, COMFY_OUTPUT_DIR, COMFY_WORKFLOW_PATH  # noqa: E402

WIDTH, HEIGHT = 1344, 768
CHECKPOINT = "RealVisXL_V5.0_fp16.safetensors"

NEGATIVE = (
    "text, letters, words, watermark, logo, label, packaging, bottle, signage, "
    "cartoon, anime, illustration, 3d render, cgi, plastic look, oversaturated, "
    "blurry, low resolution, jpeg artifacts, distorted, deformed leaves, "
    "duplicated plants, people, hands, faces"
)

OPTIONS = [
    {
        "name": "A_wide_room",
        "note": "Wide grow-room interior. Closest to the current hero's message.",
        "prompt": (
            "professional photograph of a clean indoor grow room interior, "
            "LED bar grow lights mounted overhead casting warm golden light, "
            "healthy mature flowering cannabis plants standing tall in the centre "
            "and rear of the room, rows of vibrant vegetables and herbs in the "
            "foreground -- bell peppers, leaf lettuce, basil, cabbage -- "
            "reflective white tent walls, neat irrigation lines, "
            "shallow depth of field, crisp detail on the leaves, "
            "commercial horticulture photography, wide cinematic framing"
        ),
    },
    {
        "name": "B_under_canopy",
        "note": "Low angle looking down a row. More dramatic, more 'grower'.",
        "prompt": (
            "professional photograph taken from a low angle looking down a row "
            "inside an indoor grow tent, dense healthy cannabis canopy overhead "
            "with visible trichomes and thick colas, LED bar lights flaring "
            "warmly through the leaves, leafy greens and herbs growing at floor "
            "level in the foreground, atmospheric haze, strong depth, "
            "rich green and amber colour palette, sharp macro detail on foliage, "
            "commercial horticulture photography, wide cinematic framing"
        ),
    },
    {
        "name": "C_bright_modern",
        "note": "Brighter, cleaner, more 'premium supply company'. Fits 'upgrading my image'.",
        "prompt": (
            "professional photograph of a modern well-organised indoor "
            "hydroponic grow facility, bright clean neutral-white LED bar "
            "lighting, tidy rows of thriving cannabis plants alongside lettuce, "
            "basil and pepper plants in matching containers, white and light grey "
            "surfaces, neat tubing and reservoirs, spotless floor, "
            "bright airy premium retail catalogue aesthetic, crisp focus "
            "throughout, high key lighting, wide cinematic framing"
        ),
    },
]


async def run_one(client: httpx.AsyncClient, workflow: dict, opt: dict, seed: int) -> dict:
    wf = json.loads(json.dumps(workflow))
    wf["4"]["inputs"]["ckpt_name"] = CHECKPOINT
    wf["5"]["inputs"]["width"] = WIDTH
    wf["5"]["inputs"]["height"] = HEIGHT
    wf["6"]["inputs"]["text"] = opt["prompt"]
    wf["7"]["inputs"]["text"] = NEGATIVE
    wf["3"]["inputs"]["seed"] = seed
    wf["9"]["inputs"]["filename_prefix"] = f"hero_{opt['name']}"

    resp = await client.post(f"{COMFY_HOST}/prompt", json={"prompt": wf})
    resp.raise_for_status()
    prompt_id = resp.json()["prompt_id"]

    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        await asyncio.sleep(2.0)
        try:
            data = (await client.get(f"{COMFY_HOST}/history/{prompt_id}")).json()
        except (httpx.HTTPError, ValueError):
            continue
        if prompt_id in data:
            entry = data[prompt_id]
            status = entry.get("status", {})
            if status.get("status_str") != "success":
                return {"name": opt["name"], "error": json.dumps(status.get("messages", []))[:300]}
            fn = entry["outputs"]["9"]["images"][0]["filename"]
            return {
                "name": opt["name"],
                "note": opt["note"],
                "seed": seed,
                "path": os.path.join(COMFY_OUTPUT_DIR, fn),
            }
    return {"name": opt["name"], "error": "timed out after 600s"}


async def main() -> None:
    # 16GB card: only one big thing on the GPU at a time.
    try:
        import llm_router
        llm_router.unload_all_models()
        print("[vram] unloaded LLMs")
    except Exception as e:  # noqa: BLE001
        print(f"[vram] could not unload LLMs ({e}) -- continuing")

    print("[comfy] starting (cold start ~25s)...")
    if not await comfy_image.ensure_running():
        print("ERROR: ComfyUI would not start. Check tools/ComfyUI and the server log.")
        return
    print("[comfy] up")

    with open(COMFY_WORKFLOW_PATH, encoding="utf-8") as fh:
        workflow = json.load(fh)

    results = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, opt in enumerate(OPTIONS):
            t0 = time.monotonic()
            print(f"[{i+1}/{len(OPTIONS)}] {opt['name']} ...", flush=True)
            res = await run_one(client, workflow, opt, seed=770001 + i)
            res["seconds"] = round(time.monotonic() - t0, 1)
            print(f"    -> {res.get('path') or res.get('error')}  ({res['seconds']}s)")
            results.append(res)

    out = os.path.join(ROOT, "data", "hero_options.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"width": WIDTH, "height": HEIGHT, "checkpoint": CHECKPOINT,
                   "results": results}, fh, indent=1)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    asyncio.run(main())
