"""Plant test 2 (Barry: "so Z image didnt do bad? tes on another plant"). Yarrow and stinging nettle, the same
prompt through Z-Image (reel engine) and Qwen-Image, vertical. Nettle is the hard one: drawn badly it looks like
cannabis."""
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

OUT = os.path.join(ROOT, "data", "plant_knowledge_test2_2026_09_24")
PLANTS = {
    "yarrow": "Botanical nature photograph of yarrow (Achillea millefolium) in a summer meadow: feathery, finely "
              "divided fern-like leaves, flat-topped clusters of tiny white flowers on upright stems. Natural "
              "daylight, sharp focus, realistic",
    "nettle": "Botanical nature photograph of stinging nettle (Urtica dioica) at the edge of a woodland path: "
              "opposite heart-shaped leaves with coarsely toothed edges and pointed tips, covered in fine stinging "
              "hairs, square stems, drooping strings of tiny green flowers where the leaves meet the stem. Natural "
              "daylight, sharp focus, realistic",
}


async def main():
    os.makedirs(OUT, exist_ok=True)
    while comfy_image.render_in_progress():
        await asyncio.sleep(20)
    t = time.time()
    paths = await reel_builder._render_stills(list(PLANTS.values()), "planttest2", print, reel_builder.FORMATS["short"])
    for name, p in zip(PLANTS, paths):
        shutil.copy2(p, os.path.join(OUT, f"{name}_zimage.png"))
    print(f"z-image both {time.time() - t:.0f}s", flush=True)
    await llm_router.unload_all_models()
    for name, prompt in PLANTS.items():
        t = time.time()
        r = await comfy_image.generate_image(prompt, None, "qwen-image", width=928, height=1664)
        if r.get("error"):
            print(name, "qwen FAILED", r["error"], flush=True)
            continue
        shutil.copy2(r["path"], os.path.join(OUT, f"{name}_qwen.png"))
        print(f"{name} qwen {time.time() - t:.0f}s", flush=True)


asyncio.run(main())
