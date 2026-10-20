"""Fix Tazz's eyes to canon (pink and blue double-ringed irises) on the new
renders before LoRA training. Barry, 2026-09-24: "should be pink and blue" /
"do tazz eyes dont fuck it up".

    venv/Scripts/python.exe scripts/fix_tazz_eyes_2026_09_24.py <src> [<src> ...]

Qwen-Image-Edit (Apache, local), ONE change per pass with a preservation
clause. Big frames are scaled to 1328 long edge first (Qwen-Edit takes its
output size from image 1 and a 2304px frame is slow and memory heavy).
Originals are never touched; results land in data/zimage_lora/tazz_eyefix/.
Owns the render flag with its own token.
"""
import asyncio, os, shutil, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import comfy_image  # noqa: E402
import llm_router  # noqa: E402
import qwen_edit  # noqa: E402
from config import COMFY_DIR  # noqa: E402
from PIL import Image  # noqa: E402

FLAG = os.path.join(ROOT, "data", "video_rendering.flag")
TOKEN = f"tazz-eyes-{time.time()}"
OUT = os.path.join(ROOT, "data", "zimage_lora", "tazz_eyefix")
INSTRUCTION = (
    "Change only the irises of the woman's eyes so each iris is a double ring: "
    "a pink inner ring and a blue outer ring, natural and non-glowing, with a dark "
    "pupil and normal white sclera. Keep her face, skin, ears, braids, expression, "
    "clothing, weapon, pose, lighting and background exactly the same."
)


async def main(srcs):
    os.makedirs(OUT, exist_ok=True)
    if comfy_image.render_in_progress():
        raise SystemExit("a render is already running")
    open(FLAG, "w").write(TOKEN)
    try:
        await llm_router.unload_all_models()
        if not await comfy_image.ensure_running(timeout_s=600, mode="image"):
            raise SystemExit("ComfyUI did not start")
        for src in srcs:
            name = os.path.splitext(os.path.basename(src))[0]
            staged = f"tazz_eyefix_src_{name[-8:]}.png"
            im = Image.open(src).convert("RGB")
            if max(im.size) > 1328:
                im.thumbnail((1328, 1328), Image.LANCZOS)
            im.save(os.path.join(COMFY_DIR, "input", staged))
            t0 = time.time()
            path = qwen_edit.run([staged], INSTRUCTION, prefix="tazz_eyefix")
            got = os.path.join(COMFY_DIR, "output", os.path.basename(path))
            dst = os.path.join(OUT, name + "_eyes.png")
            shutil.copy(got, dst)
            print(f"{name}: {time.time() - t0:.0f}s -> {dst}", flush=True)
    finally:
        try:
            if open(FLAG).read().strip() == TOKEN:
                os.remove(FLAG)
        except OSError:
            pass


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
