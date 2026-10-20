"""Barry 2026-10-19: "generate a 5 second test clip with the effects" (a TEST, to see before the 2-part Halloween Long;
delete from her after). Built by the office from HER shot text, word for word (her reply to that ask), through her own
builder pieces: her still restaged from her face + body refs (reel_builder._her_still), LTX-2.5 image-to-video 5 s with
her text as the motion direction, then the effects she named (ritual, sparks, smoke, lightning, sigil:helm). Silent: she
wrote a picture, no spoken line. Owns the card like her queue builds. Output: data/fx_test_clip_2026_10_19/ and a copy
in Desktop\\Ilnora's Videos\\_TEST effects clip 2026-10-19\\ (raw + with effects)."""
import asyncio, json, os, re, shutil, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import comfy_image, config, fx, llm_router, reel_builder  # noqa: E402

D = os.path.join(ROOT, "data", "fx_test_clip_2026_10_19")
OUT = os.path.join(os.path.expanduser("~"), "Desktop", "Ilnora's Videos", "_TEST effects clip 2026-10-19")
FX = ["ritual", "sparks", "smoke", "lightning", "sigil:helm"]


def log(s):
    print(time.strftime("%H:%M:%S"), s, flush=True)


async def main():
    os.environ.pop("__COMPAT_LAYER", None)
    os.makedirs(D, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    rep = json.load(open(os.path.join(ROOT, "data", "review_2026_10_18", "chain", "fx_test_go3.reply.json"), encoding="utf-8"))
    shot = " ".join(re.search(r"```image\s*\n(.+?)```", rep["reply"], re.S).group(1).split())
    open(os.path.join(D, "her_shot.txt"), "w", encoding="utf-8").write(shot)
    fmt = reel_builder.FORMATS["short"]
    scene = {"narration": "", "show": "self", "shot": shot, "motion_prompt": shot}
    token = comfy_image.REEL_ACTIVE.set(True)
    open(comfy_image._REEL_MARK, "w").write("TEST effects clip (Barry's ask)")
    try:
        await llm_router.unload_all_models()
        t0 = time.time()
        still = await reel_builder._her_still("ilnora", scene, "short", D, 0, log)
        if not still:
            log("her still failed -- stopping"); return
        log(f"still in {time.time() - t0:.0f}s")
        inp = os.path.join(config.COMFY_DIR, "input")
        name = "fxtest_still.png"
        shutil.copy2(still, os.path.join(inp, name))
        t0 = time.time()
        r = await comfy_image.generate_video(shot, duration_s=5, width=576, height=1024, start_frame=name)
        log(f"motion: {'ok' if r.get('path') else r.get('error')} in {time.time() - t0:.0f}s")
        if not r.get("path"):
            return
        raw = os.path.join(D, "raw.mp4")
        reel_builder._motion_scene_clip(r["path"], 5.0, raw, fmt, clip_s=5)
        withfx = os.path.join(D, "with_effects.mp4")
        shutil.copy2(raw, withfx)
        fx.apply(withfx, FX, 5.0, fmt, D, 0, log)
        shutil.copy2(still, os.path.join(OUT, "her_still.png"))
        shutil.copy2(raw, os.path.join(OUT, "test clip - no effects.mp4"))
        shutil.copy2(withfx, os.path.join(OUT, "test clip - with effects.mp4"))
        open(os.path.join(OUT, "her shot (her words).txt"), "w", encoding="utf-8").write(
            shot + "\n\nEffects: " + ", ".join(FX) + "\nBuilt by the office from her shot; a test, not one of her videos.\n")
        log(f"DONE -> {OUT}")
    finally:
        comfy_image.REEL_ACTIVE.reset(token)
        try:
            os.remove(comfy_image._REEL_MARK)
        except OSError:
            pass


asyncio.run(main())
