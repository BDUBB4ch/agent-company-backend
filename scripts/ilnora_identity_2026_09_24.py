"""Barry 2026-09-24: Ilnora = face from A (agent_ref_ilnora.png), hair from B (black + silver, no copper),
body from C (the 2026-09-19 full body). Three Qwen-Image-Edit passes, one change each (the edit skill's rule):
  1. A with the copper ends recoloured black        -> new face reference
  2. C with the copper ends recoloured black        -> body, hair fixed
  3. pass-2 body with pass-1 face put on it         -> new full body
Nothing is installed or locked here -- Barry picks from the results first."""
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

INP = os.path.join(comfy_image.COMFY_DIR, "input")
OUT = os.path.join(ROOT, "data", "identity", "ilnora", "candidates")
HAIR = ("Recolor only the copper-orange ends of her hair to glossy jet black, so her long wavy hair is black "
        "with soft silver-grey streaks sweeping back from the front. Keep her face, expression, eyes, skin, "
        "the hair's shape, length and waves, her clothing, the pose, lighting, background and framing exactly "
        "the same.")
FACE = ("Give the woman in image 1 the exact face of the woman in image 2: the same face shape, eyes, brows, "
        "nose, lips, skin and age lines. Keep image 1's hair, dress, body, pose, hands, lighting, room and "
        "framing exactly the same.")


async def one(sources, instruction, prefix, name):
    t0 = time.time()
    r = await comfy_image.edit_image(sources, instruction, prefix=prefix)
    if r.get("error"):
        raise SystemExit(f"{name}: {r['error']}")
    dest = os.path.join(OUT, name)
    shutil.copy2(r["path"], dest)
    print(f"{name}: {time.time() - t0:.0f}s seed {r['seed']}", flush=True)
    return dest


async def main():
    os.makedirs(OUT, exist_ok=True)
    shutil.copy2(os.path.join(ROOT, "data", "scene_backups", "ilnora_ref_wholefigure_20260919_174826.png"),
                 os.path.join(INP, "ilnora_body_c.png"))
    await llm_router.unload_all_models()
    face = await one(["agent_ref_ilnora.png"], HAIR, "ilnora_id_face", "1_face_black_hair.png")
    await one(["ilnora_body_c.png"], HAIR, "ilnora_id_body", "2_body_black_hair.png")
    shutil.copy2(face, os.path.join(INP, "ilnora_face_new.png"))
    shutil.copy2(os.path.join(OUT, "2_body_black_hair.png"), os.path.join(INP, "ilnora_body_black.png"))
    await one(["ilnora_body_black.png", "ilnora_face_new.png"], FACE, "ilnora_id_full", "3_body_face_a.png")


asyncio.run(main())
