"""Ilnora try 5 with a slightly fuller bust (Barry 2026-09-25: "slightly larger breasts? shes healthy, not big just
slightly bigger"). One change, everything else kept. Wording avoids the words that switch on the adult add-on."""
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

SRC = os.path.join(ROOT, "data", "identity", "ilnora", "candidates", "5_body_headless_dress_ref.png")
INSTRUCTION = ("Give the woman a slightly fuller bust -- a small, natural change for a healthy woman, not large. "
               "Keep her exact face, expression, age, long wavy black hair with the silver streak, the emerald-green "
               "dress with black lace sleeves and gold belt fitted the same way, her pose, hands, the candlelit room, "
               "lighting and framing exactly the same. Photographic, natural.")


async def main():
    shutil.copy2(SRC, os.path.join(comfy_image.COMFY_DIR, "input", "ilnora_try5_src.png"))
    while comfy_image.render_in_progress():
        await asyncio.sleep(20)
    await llm_router.unload_all_models()
    t = time.time()
    r = await comfy_image.edit_image(["ilnora_try5_src.png"], INSTRUCTION, prefix="ilnora_try5_bust")
    if r.get("error"):
        print("FAILED:", r["error"], flush=True)
        return
    out = os.path.join(ROOT, "data", "identity", "ilnora", "candidates", "6_try5_fuller_bust.png")
    shutil.copy2(r["path"], out)
    shutil.copy2(r["path"], r"C:\Users\Owner\Downloads\Ilnora_for_Higgsfield\Ilnora_long_hair_full_body_v2.png")
    print(f"done in {time.time() - t:.0f}s seed {r['seed']}", flush=True)


asyncio.run(main())
