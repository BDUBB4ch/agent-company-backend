"""Barry's agreed queue, 2026-09-24 evening, one GPU job at a time:
  1. Chatterbox Turbo voice samples (fixed: setuptools<81 for the watermarker)
  2. Ilnora full body: restaged from her NEW face (image 1 = identity) wearing body C's dress (image 2),
     hair long, just past her chest (Barry: "maybe just past her breasts")
Elliot's still size test comes after, separately."""
import asyncio
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import comfy_image  # noqa: E402
import llm_router  # noqa: E402

FLAG = os.path.join(ROOT, "data", "video_rendering.flag")
T = os.path.join(ROOT, "tools", "tts")
VOICES = os.path.join(ROOT, "data", "voice_bakeoff_2026_09_24")
CAND = os.path.join(ROOT, "data", "identity", "ilnora", "candidates")
INP = os.path.join(comfy_image.COMFY_DIR, "input")
BODY = ("Show the woman from image 1 in a full-length portrait from head to knees, standing in her candlelit "
        "apothecary bedroom at night, one hand resting on a wooden dresser with herb bottles, dried herbs and a lit "
        "candle, bookshelves and a moonlit window behind her. She wears the dress from image 2: sheer black lace "
        "sleeves, an emerald green bodice trimmed in black lace, a gold belt, gold embroidered vines down the green "
        "skirt and a sheer black lace lower skirt. Her long wavy jet-black hair with silver-grey streaks at the front "
        "falls over her shoulders and past her chest, ending just below her breasts. Keep her exact face, eyes, skin, "
        "age and expression from image 1. Photographic, natural skin texture, soft warm candlelight.")


async def main():
    while comfy_image.render_in_progress():
        await asyncio.sleep(20)
    token = "chatterbox-2026-09-24"
    with open(FLAG, "w") as fh:
        fh.write(token)
    try:
        await llm_router.unload_all_models()
        await comfy_image.stop_server()
        py = os.path.join(T, "chatterbox", ".venv", "Scripts", "python.exe")
        for ref in ("voxcpm_design_ref.wav", "qwen_design_ref.wav"):
            t = time.time()
            p = subprocess.run([py, os.path.join(T, "bakeoff_gen.py"), "chatterbox", VOICES, os.path.join(VOICES, ref)],
                               capture_output=True, text=True)
            print(p.stdout.strip(), f"({time.time() - t:.0f}s)" if not p.returncode else "FAILED\n" + p.stderr[-1200:],
                  flush=True)
    finally:
        try:
            if open(FLAG).read().strip() == token:
                os.remove(FLAG)
        except OSError:
            pass
    # 2. the body -- edit_image owns the flag itself
    shutil.copy2(os.path.join(ROOT, "data", "scene_backups", "ilnora_ref_wholefigure_20260919_174826.png"),
                 os.path.join(INP, "ilnora_body_c.png"))
    t = time.time()
    r = await comfy_image.edit_image(["ilnora_face_new.png", "ilnora_body_c.png"], BODY, prefix="ilnora_id_body2")
    if r.get("error"):
        print("body FAILED:", r["error"], flush=True)
        return
    shutil.copy2(r["path"], os.path.join(CAND, "4_body_from_new_face_long_hair.png"))
    print(f"4_body_from_new_face_long_hair.png: {time.time() - t:.0f}s seed {r['seed']}", flush=True)


asyncio.run(main())
