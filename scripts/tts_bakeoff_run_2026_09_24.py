"""Voice bake-off driver (office venv). Waits for the card to be free, owns data/video_rendering.flag, unloads the
LLMs and stops ComfyUI, then runs each engine in its own venv one after another, and clears its own flag.
Also renders today's Kokoro voice reading the same script, for comparison."""
import asyncio
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import comfy_image  # noqa: E402
import llm_router  # noqa: E402

T = os.path.join(ROOT, "tools", "tts")
OUT = os.path.join(ROOT, "data", "voice_bakeoff_2026_09_24")
FLAG = os.path.join(ROOT, "data", "video_rendering.flag")
GEN = os.path.join(T, "bakeoff_gen.py")


def run(engine, *extra):
    py = os.path.join(T, engine, ".venv", "Scripts", "python.exe")
    t = time.time()
    p = subprocess.run([py, GEN, engine, OUT, *extra], capture_output=True, text=True)
    print(p.stdout.strip(), flush=True)
    if p.returncode:
        print(f"{engine} FAILED ({time.time() - t:.0f}s):\n{p.stderr[-1500:]}", flush=True)
    else:
        print(f"{engine} total {time.time() - t:.0f}s", flush=True)


async def main():
    os.makedirs(OUT, exist_ok=True)
    import kokoro_tts
    sys.path.insert(0, T)
    script = open(GEN, encoding="utf-8").read().split('SCRIPT = (')[1].split(')\n')[0]
    text = "".join(eval("(" + script + ")"))
    with open(os.path.join(OUT, "0_kokoro_today.wav"), "wb") as fh:
        fh.write(kokoro_tts.synthesize("ilnora", text))
    print("kokoro done", flush=True)
    while comfy_image.render_in_progress():
        await asyncio.sleep(20)
    token = "voice-bakeoff-2026-09-24"
    with open(FLAG, "w") as fh:
        fh.write(token)
    try:
        await llm_router.unload_all_models()
        await comfy_image.stop_server()
        run("voxcpm")
        run("qwen3tts")
        for ref in ("voxcpm_design_ref.wav", "qwen_design_ref.wav"):
            if os.path.isfile(os.path.join(OUT, ref)):
                run("chatterbox", os.path.join(OUT, ref))
    finally:
        try:
            if open(FLAG).read().strip() == token:
                os.remove(FLAG)
        except OSError:
            pass


asyncio.run(main())
