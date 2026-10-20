"""Ilnora's NEUTRAL body reference (Barry 2026-10-03: "i want her body too, so we use her face and body, but prompt a
new outfit or color" -> a plain-clothes version so the green dress can't bleed into new outfits). Qwen-Image-Edit
(Apache 2.0) on her LOCKED body picture: clothes changed, everything else kept. Writes CANDIDATES only --
data/identity/ilnora/body_neutral_candidate_<n>.png; nothing uses them until Barry picks one."""
import asyncio
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import comfy_image  # noqa: E402
import config  # noqa: E402
import llm_router  # noqa: E402

ID = os.path.join(ROOT, "data", "identity", "ilnora")
INSTRUCTION = ("Change her clothing to a plain, simple, fitted black short-sleeve t-shirt and plain fitted black "
               "leggings, barefoot. Keep her face, hair, skin, age, body shape, proportions, pose, expression, the "
               "camera angle, the framing and the background exactly the same. Photographic, natural.")


async def main() -> None:
    src = "ilnora_body_for_neutral.png"
    shutil.copy2(os.path.join(ID, "body.png"), os.path.join(config.COMFY_DIR, "input", src))
    await llm_router.unload_all_models()
    for n, seed in enumerate((11, 29), 1):
        r = await comfy_image.edit_image([src], INSTRUCTION, seed=seed, prefix="ilnora_neutral")
        if not r.get("path"):
            print("take", n, "failed:", r.get("error"))
            continue
        out = os.path.join(ID, f"body_neutral_candidate_{n}.png")
        shutil.copy2(r["path"], out)
        print("take", n, "->", out)


if __name__ == "__main__":
    asyncio.run(main())
