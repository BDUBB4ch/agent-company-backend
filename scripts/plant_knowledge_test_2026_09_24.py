"""Does the picture engine KNOW the plant? (Barry 2026-09-24: "Qwen should know what these plants look like")
Same mugwort prompt -- scientific name + botanical description -- through Z-Image Turbo (vertical, the reel
engine) and Qwen-Image (the business engine, Apache-2.0) via the office's own generate_image path."""
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
import reel_builder  # noqa: E402

OUT = os.path.join(ROOT, "data", "plant_knowledge_test_2026_09_24")
PROMPT = ("Botanical nature photograph of common mugwort (Artemisia vulgaris) growing wild at the edge of a country "
          "road: tall reddish-purple stems, deeply cut pinnately lobed leaves like chrysanthemum leaves, dark green "
          "on top with silvery-white woolly undersides, small grey-green flower buds in loose spikes at the top. "
          "Natural daylight, sharp focus, realistic")


async def main():
    os.makedirs(OUT, exist_ok=True)
    while comfy_image.render_in_progress():
        await asyncio.sleep(20)
    t = time.time()
    p = await reel_builder._render_stills([PROMPT], "planttest", print, reel_builder.FORMATS["short"])
    shutil.copy2(p[0], os.path.join(OUT, "1_zimage.png"))
    print(f"z-image {time.time() - t:.0f}s", flush=True)
    for name, kw in [("2_qwen_image_square", {}), ("3_qwen_image_portrait", {"width": 928, "height": 1664})]:
        await llm_router.unload_all_models()
        t = time.time()
        r = await comfy_image.generate_image(PROMPT, None, "qwen-image", **kw)
        if r.get("error"):
            print(name, "FAILED", r["error"], flush=True)
            continue
        shutil.copy2(r["path"], os.path.join(OUT, name + ".png"))
        print(f"{name} {time.time() - t:.0f}s model {r.get('model')}", flush=True)


asyncio.run(main())
