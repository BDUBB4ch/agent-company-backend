"""Test of the 3 fixes (Barry 2026-10-04: "go, fix all three") through reel_builder._her_still, the function her
videos call: (1) wide Long frame drawn at its own size, (2) speed with the small face reference, (3) a shot naming no
clothes keeps the outfit of her last shot. -> data/reels/_her_shot_test/ + test panel assets + test.log."""
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
import reel_builder as R  # noqa: E402

D = os.path.join(ROOT, "data", "reels", "_her_shot_test")
PANEL = os.path.join(os.path.dirname(ROOT), "AgentDashboard", "assets", "test_panel")
LOG = os.path.join(D, "test.log")
TESTS = [
    ("short_gown", "short", "Deep plum velvet gown, at a dark oak table with a carved pumpkin beside me, both hands "
                            "resting on the table, medium close-up, candlelight from the left", ""),
    ("short_carry", "short", "Leaning in close to the camera with a sly grin, one finger raised", "Deep plum velvet gown"),
    ("long_gown", "long", "Deep plum velvet gown, at a dark oak table with a carved pumpkin beside me, both hands "
                          "resting on the table, medium shot, candlelight from the left", ""),
]


def log(m: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {m}"
    print(line, flush=True)
    open(LOG, "a", encoding="utf-8").write(line + "\n")


async def main() -> None:
    os.makedirs(D, exist_ok=True)
    while comfy_image.render_in_progress() or comfy_image.reel_building():
        await asyncio.sleep(30)
    await llm_router.unload_all_models()
    for i, (name, form, shot, last) in enumerate(TESTS):
        t0 = time.time()
        out = await R._her_still("ilnora", {"show": "self", "shot": shot}, form, D, i, log, last_outfit=last)
        if not out:
            log(f"{name}: FAILED")
            continue
        dst = os.path.join(PANEL, f"ilnora_shotfix_{name}.png")
        shutil.copy2(out, dst)
        from PIL import Image
        with Image.open(out) as im:
            log(f"{name}: {im.size[0]}x{im.size[1]} in {time.time() - t0:.0f}s -> {os.path.basename(dst)}")
    log("done")


if __name__ == "__main__":
    asyncio.run(main())
