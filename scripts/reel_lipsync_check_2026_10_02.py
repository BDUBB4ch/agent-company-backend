"""Check reel_builder._lipsync (the code build_reel now runs on her animated parts) on the moving clip the 10-02
alive test already rendered -- skips the 15-min LTX step. -> data/reels/_motion_test/wired_c000.mp4 + frames."""
import asyncio
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import reel_builder  # noqa: E402

D = os.path.join(ROOT, "data", "reels", "_motion_test")


async def main() -> None:
    clip = os.path.join(D, "wired_c000.mp4")
    shutil.copy2(os.path.join(D, "her_moving.mp4"), clip)
    sec = 10.1 + reel_builder.PAD_S                     # her line + the breath, as build_reel pads it
    reel_builder._motion_scene_clip(os.path.join(D, "her_moving.mp4"), sec, clip, reel_builder.FORMATS["short"])
    print("lipsync_on:", reel_builder._lipsync_on(), flush=True)
    ok = await reel_builder._lipsync(clip, os.path.join(D, "v000.wav"), sec, print)
    print("ok:", ok, "flag left:", os.path.exists(os.path.join(ROOT, "data", "video_rendering.flag")), flush=True)
    ff = reel_builder._ffmpeg()
    print(subprocess.run([ff, "-hide_banner", "-i", clip], capture_output=True, text=True).stderr.splitlines()[-4:])
    for k, ss in enumerate((1.0, 4.0, 7.0, 10.0)):
        subprocess.run([ff, "-y", "-loglevel", "error", "-ss", str(ss), "-i", clip, "-frames:v", "1",
                        os.path.join(D, f"wired_f{k}.jpg")])
    # with her voice muxed back on, so Barry can watch + listen to exactly what a reel part will look like
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", clip, "-i", os.path.join(D, "v000.wav"), "-c:v", "copy",
                    "-c:a", "aac", "-shortest", os.path.join(D, "wired_with_voice.mp4")])
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
