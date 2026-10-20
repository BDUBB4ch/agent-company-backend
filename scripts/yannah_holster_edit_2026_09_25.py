"""Yannah full body from Barry's picture, gun holstered (his pick 2026-09-25: "Holster the gun first").
One change: the white pistol goes into her thigh holster, hands empty. The result is checked before it becomes her
body reference (char_ref_yannah / char_yannah_body)."""
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

SRC = os.path.join(ROOT, "data", "higgs_zips_2026_09_24", "refs", "yannah_body_barry_gun_in_hand.png")
OUT = os.path.join(ROOT, "data", "higgs_zips_2026_09_24", "refs", "yannah_body_barry_holstered.png")
INSTRUCTION = ("Put the white pistol away into the holster strapped to her right thigh, so both of her hands are empty "
               "and relaxed at her sides. Keep her exact face, eyes, pointed ears, locs with copper tips, the black "
               "tactical suit with teal piping, belt, boots, her stance, the grey concrete wall, lighting and framing "
               "exactly the same. Hyper-realistic, documentary realism.")


async def main():
    shutil.copy2(SRC, os.path.join(comfy_image.COMFY_DIR, "input", "yannah_body_barry_src.png"))
    # wait for the proof still AND its whole job to finish
    log = os.path.join(ROOT, "data", "yannah_newref_test.log")
    while True:
        done = os.path.isfile(log) and any(("yannah_464_newref" in ln) for ln in open(log, encoding="utf-8",
                                                                                       errors="ignore"))
        if done and not comfy_image.render_in_progress():
            break
        await asyncio.sleep(15)
    await llm_router.unload_all_models()
    t = time.time()
    r = await comfy_image.edit_image(["yannah_body_barry_src.png"], INSTRUCTION, prefix="yannah_holstered")
    if r.get("error"):
        print("FAILED:", r["error"], flush=True)
        return
    shutil.copy2(r["path"], OUT)
    print(f"done in {time.time() - t:.0f}s seed {r['seed']}", flush=True)


asyncio.run(main())
