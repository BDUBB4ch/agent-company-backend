"""Anchor-voice test (Barry 2026-09-25: "the voice changes too much" / "almost every image change the voice changes").
The 15 narration lines of test reel 3, regenerated through her locked voice in ANCHOR mode (every line continues
from the same 16 s clip), stitched with the reel's 0.35 s breaths, + per-line pitch from the pitch guard."""
import asyncio
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
os.chdir(os.path.join(ROOT, "backend"))
import comfy_image  # noqa: E402
import llm_router  # noqa: E402
import reel_builder as rb  # noqa: E402

OUT = os.path.join(ROOT, "data", "voice_anchor_test_2026_09_25")
FLAG = os.path.join(ROOT, "data", "video_rendering.flag")


async def main():
    os.makedirs(OUT, exist_ok=True)
    import importlib.util
    spec = importlib.util.spec_from_file_location("t3", os.path.join(ROOT, "scripts", "reel_test3_2026_09_24.py"))
    t3 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(t3)
    lines = [s["narration"] for s in t3.PACKAGE["scenes"]]
    with open(os.path.join(OUT, "lines.json"), "w", encoding="utf-8") as fh:
        json.dump(lines, fh)
    # wait for Yannah's BOTH passes (the card is free for a moment between them -- don't steal it)
    ylog = os.path.join(ROOT, "data", "yannah_photoreal.log")
    while True:
        done = os.path.isfile(ylog) and any(ln.startswith(("body:", "body FAILED")) for ln in open(ylog, encoding="utf-8",
                                                                                                    errors="ignore"))
        if done and not comfy_image.render_in_progress():
            break
        await asyncio.sleep(20)
    token = "voice-anchor-test"
    with open(FLAG, "w") as fh:
        fh.write(token)
    try:
        await llm_router.unload_all_models()
        await comfy_image.stop_server()
        p = subprocess.run([rb.VOXCPM_PY, rb.VOXCPM_LINES, os.path.join(ROOT, "data", "identity", "ilnora", "voice"),
                            os.path.join(OUT, "lines.json"), OUT], capture_output=True, text=True)
        print(p.stdout.strip()[-3000:] if p.returncode == 0 else "FAILED\n" + p.stderr[-1500:], flush=True)
    finally:
        try:
            if open(FLAG).read().strip() == token:
                os.remove(FLAG)
        except OSError:
            pass
    parts = []
    for i in range(len(lines)):
        src = os.path.join(OUT, f"v{i:03d}.wav")
        dst = os.path.join(OUT, f"p{i:03d}.wav")
        rb._run(["-i", src, "-af", "apad=pad_dur=0.35", "-ar", "48000", "-ac", "1", dst])
        parts.append(dst)
    with open(os.path.join(OUT, "list.txt"), "w") as fh:
        fh.writelines(f"file '{os.path.basename(x)}'\n" for x in parts)
    rb._run(["-f", "concat", "-safe", "0", "-i", os.path.join(OUT, "list.txt"), "-b:a", "192k",
             os.path.join(OUT, "all_lines_anchor.mp3")])
    print("stitched", flush=True)


asyncio.run(main())
