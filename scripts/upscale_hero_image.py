"""Upscale the existing homepage hero so it stops being stretched.

The live hero (attachment 23458, image-_19_.webp) is 752x1392 and sits in a
16:9 ux_banner that is ~1300px wide on desktop -- so the browser blows it up
~1.73x and it reads soft. Barry's call: keep HIS image, just make it not soft.

Nothing about the composition or crop changes. 4x-UltraSharp reconstructs
detail, then we scale back to 1600px wide (comfortably over the 1300px band,
under the point where filesize hurts).

Run:  ../venv/Scripts/python.exe scripts/upscale_hero_image.py
"""
import asyncio
import io
import json
import os
import sys
import time

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import comfy_image  # noqa: E402
from config import COMFY_HOST, COMFY_OUTPUT_DIR  # noqa: E402

SRC_URL = "https://bdubbgrowsllc.com/wp-content/uploads/2025/08/image-_19_.webp"
INPUT_DIR = os.path.join(ROOT, "tools", "ComfyUI", "input")
STAGED_NAME = "hero_src_for_upscale.png"
UPSCALER = "4x-UltraSharp.pth"
TARGET_W = 1600  # source is 752 wide; band is ~1300


def stage_source() -> tuple[int, int]:
    from PIL import Image
    r = httpx.get(SRC_URL, timeout=60.0)
    r.raise_for_status()
    im = Image.open(io.BytesIO(r.content)).convert("RGB")
    os.makedirs(INPUT_DIR, exist_ok=True)
    im.save(os.path.join(INPUT_DIR, STAGED_NAME), "PNG")
    print(f"[src] {im.width}x{im.height} -> {STAGED_NAME}")
    return im.width, im.height


def build_workflow(src_w: int, src_h: int) -> dict:
    target_h = round(src_h * (TARGET_W / src_w))
    # keep it even
    target_h -= target_h % 2
    print(f"[plan] 4x upscale then scale down to {TARGET_W}x{target_h}")
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": STAGED_NAME}},
        "2": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": UPSCALER}},
        "3": {"class_type": "ImageUpscaleWithModel",
              "inputs": {"upscale_model": ["2", 0], "image": ["1", 0]}},
        "4": {"class_type": "ImageScale",
              "inputs": {"image": ["3", 0], "upscale_method": "lanczos",
                         "width": TARGET_W, "height": target_h, "crop": "disabled"}},
        "5": {"class_type": "SaveImage",
              "inputs": {"images": ["4", 0], "filename_prefix": "hero_upscaled"}},
    }


async def main() -> None:
    src_w, src_h = stage_source()

    try:
        import llm_router
        await llm_router.unload_all_models()
        print("[vram] LLMs unloaded")
    except Exception as e:  # noqa: BLE001
        print(f"[vram] unload skipped ({e})")

    print("[comfy] starting...")
    if not await comfy_image.ensure_running():
        print("ERROR: ComfyUI would not start.")
        return
    print("[comfy] up")

    wf = build_workflow(src_w, src_h)
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(f"{COMFY_HOST}/prompt", json={"prompt": wf})
        if resp.status_code != 200:
            print(f"ERROR: ComfyUI rejected workflow: {resp.text[:500]}")
            return
        pid = resp.json()["prompt_id"]

        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            await asyncio.sleep(2.0)
            try:
                data = (await client.get(f"{COMFY_HOST}/history/{pid}")).json()
            except (httpx.HTTPError, ValueError):
                continue
            if pid in data:
                entry = data[pid]
                st = entry.get("status", {})
                if st.get("status_str") != "success":
                    print("ERROR: " + json.dumps(st.get("messages", []))[:600])
                    return
                fn = entry["outputs"]["5"]["images"][0]["filename"]
                out = os.path.join(COMFY_OUTPUT_DIR, fn)
                print(f"\nDONE: {out}")
                try:
                    from PIL import Image
                    im = Image.open(out)
                    print(f"      {im.width}x{im.height}, {os.path.getsize(out)//1024} KB")
                except Exception:  # noqa: BLE001
                    pass
                return
    print("ERROR: timed out")


if __name__ == "__main__":
    asyncio.run(main())
