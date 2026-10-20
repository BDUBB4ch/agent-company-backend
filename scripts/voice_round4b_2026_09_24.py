"""Owns the card for VoxCPM2 round 4 (A2 with more life), then clears its own flag."""
import asyncio
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import comfy_image  # noqa: E402
import llm_router  # noqa: E402

FLAG = os.path.join(ROOT, "data", "video_rendering.flag")
T = os.path.join(ROOT, "tools", "tts")


async def main():
    while comfy_image.render_in_progress():
        await asyncio.sleep(20)
    token = "voice-round4b-2026-09-24"
    with open(FLAG, "w") as fh:
        fh.write(token)
    try:
        await llm_router.unload_all_models()
        await comfy_image.stop_server()
        p = subprocess.run([os.path.join(T, "voxcpm", ".venv", "Scripts", "python.exe"),
                            os.path.join(T, "voxcpm_lively.py"), os.path.join(ROOT, "data", "voice_round4b_2026_09_24")],
                           capture_output=True, text=True)
        print(p.stdout.strip(), flush=True)
        if p.returncode:
            print("FAILED\n" + p.stderr[-1500:], flush=True)
    finally:
        try:
            if open(FLAG).read().strip() == token:
                os.remove(FLAG)
        except OSError:
            pass


asyncio.run(main())
