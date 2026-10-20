"""Edit-step-only test (2026-10-05 06:40): the scene-first scene (D:/ComfyUI25/output/qwen_agent_00056_.png -- real
room, her green dress) + her HEAD-only crop -> face and hair only. Same instruction as reel_builder._her_still's scene
path. -> data/reels/_her_scene_first_test/faceswap.png"""
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

D = os.path.join(ROOT, "data", "reels", "_her_scene_first_test")
INP = os.path.join(comfy_image.COMFY_DIR, "input")


async def main() -> None:
    token = comfy_image.REEL_ACTIVE.set(True)
    open(comfy_image._REEL_MARK, "w").write("Ilnora face-swap test")
    try:
        await comfy_image.reel_wait_turn(print)
        await llm_router.unload_all_models()
        shutil.copy2(os.path.join(comfy_image.COMFY_DIR, "output", "qwen_agent_00056_.png"),
                     os.path.join(INP, "swaptest_scene.png"))
        shutil.copy2(os.path.join(D, "_head_check.png"), os.path.join(INP, "swaptest_head.png"))
        ins = ("Change only the woman's face and hair in image 1 to the face and hair of the woman in image 2: her "
               "exact face, eyes, nose, mouth, skin and age, and her long wavy black hair with the silver streak. Keep "
               "everything else in image 1 exactly as it is -- her clothes, her body, her pose, the place, the "
               "objects, the light and the framing. Photographic.")
        t0 = time.time()
        r = await comfy_image.edit_image(["swaptest_scene.png", "swaptest_head.png"], ins, prefix="reel_her",
                                         size=(1376, 768))
        if r.get("path"):
            shutil.copy2(r["path"], os.path.join(D, "faceswap.png"))
        print(f"done in {time.time() - t0:.0f}s: {r.get('path') or r.get('error')}", flush=True)
    finally:
        comfy_image.REEL_ACTIVE.reset(token)
        for p in (comfy_image._REEL_MARK, os.path.join(INP, "swaptest_scene.png"), os.path.join(INP, "swaptest_head.png")):
            try:
                os.remove(p)
            except OSError:
                pass


if __name__ == "__main__":
    asyncio.run(main())
