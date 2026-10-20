"""One real motion clip of Ilnora through the exact reel path (2026-10-02, Barry: "ilnora has to have life").
Waits for Derek's redraft (scripts/derek_redraft_2026_10_02.py) to finish, restarts the backend so the day's fixes are
live (only with no render flag and no Ilnora/Derek job running), then: one library photo -> reel_builder._animate
(LTX-2.5 i2v, 5 s, 576x1024) -> _motion_scene_clip filled to a 12 s line. Timed. Output in data/reels/_motion_test/."""
import asyncio
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))


def running(pattern: str) -> bool:
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object {{ $_.CommandLine "
                        f"-match '{pattern}' }}).Count"], capture_output=True, text=True)
    return (r.stdout.strip() or "0") != "0"


async def main() -> None:
    while running("derek_redraft"):
        time.sleep(30)
    print("derek done", time.strftime("%H:%M:%S"), flush=True)
    flag = os.path.join(ROOT, "data", "video_rendering.flag")
    if not os.path.exists(flag):
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "$c = Get-NetTCPConnection -LocalPort 8420 -State Listen -ErrorAction SilentlyContinue; "
                        "if ($c) { Stop-Process -Id $c.OwningProcess -Force }"], capture_output=True, timeout=30)
        time.sleep(40)
        print("backend restarted (day's fixes live)", flush=True)
    import reel_builder
    import llm_router
    await llm_router.unload_all_models()
    d = os.path.join(ROOT, "data", "reels", "_motion_test")
    os.makedirs(d, exist_ok=True)
    pic = reel_builder._self_picture("ilnora", "short", take=False)
    print("photo:", pic, flush=True)
    t0 = time.time()
    vids = await reel_builder._animate([pic], [{"show": "self", "narration": "x"}], d, "short", lambda s: print(s, flush=True))
    print(f"i2v: {vids[0]} in {time.time() - t0:.0f}s", flush=True)
    if vids[0]:
        out = os.path.join(d, "her_12s.mp4")
        reel_builder._motion_scene_clip(vids[0], 12.0, out, reel_builder.FORMATS["short"])
        print("filled 12 s clip:", out, os.path.getsize(out), "bytes", flush=True)
        for k, ss in enumerate((0.5, 3.0, 6.0, 9.5)):
            subprocess.run([reel_builder._ffmpeg(), "-y", "-loglevel", "error", "-ss", str(ss), "-i", out,
                            "-frames:v", "1", "-vf", "scale=270:480", os.path.join(d, f"frame_{k}.jpg")])
        print("frames saved", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
