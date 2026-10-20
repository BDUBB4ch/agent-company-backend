"""Barry 2026-09-25: "well we test it, its not bare breasts". Her image base line (data/identity/ilnora/image_prompt.txt,
with "Medium natural breasts.") through the office's own editor path, clothed, in an everyday scene. The log records
whether the adult add-on (XXX LoRA) chained, so the effect of the word can be judged on the picture itself."""
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

base = open(os.path.join(ROOT, "data", "identity", "ilnora", "image_prompt.txt"), encoding="utf-8").read()
base = base.split("\n\n")[1].strip()
SCENE = (" Show her waist-up in her rustic kitchen, pouring dark herbal tea from a clay teapot into a handmade cup, "
         "steam rising, dried herb bundles hanging behind her, warm window light. She wears her emerald-green dress "
         "with sheer black lace sleeves and a gold belt. Keep her exact face from image 1.")
SRC = os.path.join(ROOT, "data", "identity", "ilnora", "candidates", "5_body_headless_dress_ref.png")


async def main():
    shutil.copy2(SRC, os.path.join(comfy_image.COMFY_DIR, "input", "ilnora_try5_src.png"))
    print("adult add-on words present:", comfy_image._prompt_is_explicit(base + SCENE),
          "| add-on switch on:", comfy_image._xxx_on(), flush=True)
    while comfy_image.render_in_progress():
        await asyncio.sleep(20)
    await llm_router.unload_all_models()
    t = time.time()
    r = await comfy_image.edit_image(["ilnora_try5_src.png"], base + SCENE, prefix="ilnora_baseline_test")
    if r.get("error"):
        print("FAILED:", r["error"], flush=True)
        return
    shutil.copy2(r["path"], os.path.join(ROOT, "data", "identity", "ilnora", "candidates", "7_baseline_test_tea.png"))
    print(f"done in {time.time() - t:.0f}s seed {r['seed']}", flush=True)


asyncio.run(main())
