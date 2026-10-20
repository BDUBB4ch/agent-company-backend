"""Ilnora full body, try 5 (2026-09-24). Try 4 drifted to body C's face because the dress picture carried a face.
Now image 2 is body C cropped from the neck down (no face, no copper hair), so her new face (image 1) is the only
face the editor sees. Hair: long, just past her chest (Barry). Wording avoids the words that switch on the
adult add-on (try 4 tripped it by accident)."""
import asyncio
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import comfy_image  # noqa: E402
import llm_router  # noqa: E402
from PIL import Image  # noqa: E402

INP = os.path.join(comfy_image.COMFY_DIR, "input")
CAND = os.path.join(ROOT, "data", "identity", "ilnora", "candidates")
BODY = ("Show the woman from image 1 in a full-length portrait from head to knees, standing in her candlelit "
        "apothecary bedroom at night, one hand resting on a wooden dresser with herb bottles, dried herbs and a lit "
        "candle, bookshelves and a moonlit window behind her. She wears the dress from image 2: sheer black lace "
        "sleeves, an emerald green bodice trimmed in black lace, a gold belt, gold embroidered vines down the green "
        "skirt and a sheer black lace lower skirt. Her long wavy jet-black hair with silver-grey streaks at the front "
        "falls over her shoulders and down her front to the middle of her chest. Keep her exact face, eyes, skin, age "
        "and expression from image 1. Photographic, natural skin texture, soft warm candlelight.")


async def main():
    im = Image.open(os.path.join(ROOT, "data", "scene_backups", "ilnora_ref_wholefigure_20260919_174826.png"))
    im.convert("RGB").crop((0, 335, 1024, 1024)).save(os.path.join(INP, "ilnora_dress_c_headless.png"))
    while comfy_image.render_in_progress():
        await asyncio.sleep(20)
    await llm_router.unload_all_models()
    t = time.time()
    r = await comfy_image.edit_image(["ilnora_face_new.png", "ilnora_dress_c_headless.png"], BODY,
                                     prefix="ilnora_id_body5")
    if r.get("error"):
        print("FAILED:", r["error"], flush=True)
        return
    shutil.copy2(r["path"], os.path.join(CAND, "5_body_headless_dress_ref.png"))
    print(f"5_body_headless_dress_ref.png: {time.time() - t:.0f}s seed {r['seed']}", flush=True)


asyncio.run(main())
