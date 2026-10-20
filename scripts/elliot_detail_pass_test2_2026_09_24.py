"""Elliot still DETAIL PASS test, round 2 -- FACE PROTECTED (Barry OK'd 2026-09-24). Round 1 (30%, whole frame)
sharpened everything but changed Yannah's face. Now: 20% redraw, faces found by OpenCV and masked OUT of the
redraw (SetLatentNoiseMask), then the original face pasted back over the result with a soft edge.
---- round 1 notes ----
Elliot still DETAIL PASS test (Barry OK'd 2026-09-24, after the voices). Single character first: render #464
(Yannah, 1024x576, Qwen-Image 2.1) is enlarged to 1664x928 (the model's native 16:9) and lightly re-drawn
(denoise 0.30) by the same Qwen 2.1 model with his same prompt -- TEXT ONLY, no reference pictures, so the vision
load that froze the PC on 09-22 is not in play. Card memory is sampled the whole run (peak reported) and the
office's card guard applies (stop if pinned full). Nothing is wired into the office by this script."""
import asyncio
import json
import os
import shutil
import sqlite3
import sys
import time

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import comfy_image as ci  # noqa: E402
import llm_router  # noqa: E402

SRC_ID = 464
W, H = 1664, 928
DENOISE = 0.20
STEPS = 20
OUT = os.path.join(ROOT, "data", "elliot_detail_test2_2026_09_24")
FLAG = os.path.join(ROOT, "data", "video_rendering.flag")


async def main():
    os.makedirs(OUT, exist_ok=True)
    row = sqlite3.connect(os.path.join(ROOT, "data", "brain.db")).execute(
        "select file_path, content from approvals where id=?", (SRC_ID,)).fetchone()
    src, content = row
    prompt = content.split("Generated image concept:", 1)[-1].split("\nModel:")[0].strip()
    shutil.copy2(src, os.path.join(OUT, f"{SRC_ID}_original_1024x576.png"))
    shutil.copy2(src, os.path.join(ci.COMFY_DIR, "input", f"elliot_{SRC_ID}_src.png"))
    print("prompt:", prompt, flush=True)
    import cv2
    from PIL import Image, ImageDraw, ImageFilter
    g = cv2.cvtColor(cv2.imread(src), cv2.COLOR_BGR2GRAY)
    faces = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml").detectMultiScale(
        g, 1.1, 4, minSize=(24, 24))
    if len(faces) == 0:
        print("no face found -- not running", flush=True)
        return
    ow, oh = Image.open(src).size
    k = W / ow
    keep = Image.new("L", (W, H), 0)             # 255 = keep the original (face), 0 = redraw
    dr = ImageDraw.Draw(keep)
    for (x, y, w, h) in faces:                   # face box grown 45% so hairline, ears and jaw stay hers
        cx, cy, r = (x + w / 2) * k, (y + h / 2) * k, max(w, h) * k * 0.725
        dr.ellipse((cx - r, cy - r * 1.15, cx + r, cy + r * 1.15), fill=255)
    keep = keep.filter(ImageFilter.GaussianBlur(10))
    keep.save(os.path.join(OUT, "face_keep_mask.png"))
    Image.eval(keep, lambda v: 255 - v).convert("RGB").save(os.path.join(ci.COMFY_DIR, "input", f"elliot_{SRC_ID}_redraw_mask.png"))
    print("faces:", [list(map(int, f)) for f in faces], flush=True)

    while ci.render_in_progress():
        await asyncio.sleep(20)
    token = f"elliot-detail-test2-{SRC_ID}"
    with open(FLAG, "w") as fh:
        fh.write(token)
    try:
        await llm_router.unload_all_models()
        if not await ci.ensure_running(timeout_s=300, mode="video"):
            print("ComfyUI (video mode) did not start", flush=True)
            return
        wf = json.load(open(os.path.join(ROOT, "workflows", "comfy_qwen21_t2i_api.json"), encoding="utf-8"))
        wf["5"]["inputs"]["prompt"] = ci.normalize_mentions(prompt)
        wf["5"]["inputs"]["negative_prompt"] = ""
        del wf["7"]
        wf["30"] = {"class_type": "LoadImage", "inputs": {"image": f"elliot_{SRC_ID}_src.png"}}
        wf["31"] = {"class_type": "ImageScale", "inputs": {"image": ["30", 0], "upscale_method": "lanczos",
                                                           "width": W, "height": H, "crop": "disabled"}}
        wf["32"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["31", 0], "vae": ["3", 0]}}
        wf["33"] = {"class_type": "LoadImageMask", "inputs": {"image": f"elliot_{SRC_ID}_redraw_mask.png", "channel": "red"}}
        wf["34"] = {"class_type": "SetLatentNoiseMask", "inputs": {"samples": ["32", 0], "mask": ["33", 0]}}
        wf["8"]["inputs"].update({"latent_image": ["34", 0], "seed": 1234, "steps": STEPS, "denoise": DENOISE})
        wf["12"]["inputs"]["strength_model"] = ci.QWEN21_CHARACTER_DETAILER
        wf["10"]["inputs"]["filename_prefix"] = f"elliot_{SRC_ID}_detail2"
        t0 = time.time()
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{ci.COMFY_HOST}/prompt", json={"prompt": wf})
            if r.status_code != 200:
                print("ComfyUI refused:", r.text[:600], flush=True)
                return
            pid = r.json()["prompt_id"]
            peak, full_since = 0.0, None
            while True:
                await asyncio.sleep(5)
                used = await asyncio.to_thread(ci.gpu_dedicated_gb)
                if used is not None:
                    peak = max(peak, used)
                    if used >= ci.VRAM_GUARD_GB:
                        full_since = full_since or time.time()
                        if time.time() - full_since >= ci.VRAM_GUARD_SECONDS:
                            await c.post(f"{ci.COMFY_HOST}/interrupt")
                            print(f"GUARD STOPPED IT: card at {used:.1f} GB", flush=True)
                            return
                    else:
                        full_since = None
                h = (await c.get(f"{ci.COMFY_HOST}/history/{pid}")).json()
                if pid in h:
                    st = h[pid].get("status", {})
                    if st.get("status_str") != "success":
                        print("FAILED:", json.dumps(st.get("messages", []))[-800:], flush=True)
                        return
                    im = h[pid]["outputs"]["10"]["images"][0]
                    shutil.copy2(os.path.join(ci.COMFY_OUTPUT_DIR, im.get("subfolder", ""), im["filename"]),
                                 os.path.join(OUT, f"{SRC_ID}_detail_raw_{W}x{H}.png"))
                    # paste her ORIGINAL face back (lanczos-enlarged) through the soft mask
                    det = Image.open(os.path.join(OUT, f"{SRC_ID}_detail_raw_{W}x{H}.png")).convert("RGB")
                    org = Image.open(src).convert("RGB").resize((W, H), Image.LANCZOS)
                    Image.composite(org, det, Image.open(os.path.join(OUT, "face_keep_mask.png"))).save(
                        os.path.join(OUT, f"{SRC_ID}_detail_{W}x{H}.png"))
                    break
                if time.time() - t0 > 1800:
                    await c.post(f"{ci.COMFY_HOST}/interrupt")
                    print("timed out", flush=True)
                    return
        print(f"done in {time.time() - t0:.0f}s, card peak {peak:.1f} GB (guard at {ci.VRAM_GUARD_GB} GB)", flush=True)
    finally:
        try:
            if open(FLAG).read().strip() == token:
                os.remove(FLAG)
        except OSError:
            pass


asyncio.run(main())
