"""Barry 2026-10-05: "ok, i need 2 good ass production style minutes of 2 different plants" / "run her two turns again".
Video 1 ("Two Witches' Sisters: Belladonna & Mugwort") queued 23:55; video 2 missed its tries. So:
1. wait until her queue is idle (video 1 built, no reel flag, no queued/building job)
2. hold reel_building.flag, give her up to 3 fresh writing turns (office's standing turn + Barry's words, verbatim,
   nothing from me), release the flag -> the queue builds it (window open till 09:00).
Log: data/video_queue/queue.log"""
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import comfy_image  # noqa: E402
import video_queue as Q  # noqa: E402

BARRY = 'FROM BARRY (his words): "ok, i need 2 good ass production style minutes of 2 different plants"'


def busy() -> bool:
    return comfy_image.reel_building() or any(j.get("status") in ("queued", "building") for j in Q._jobs())


async def main() -> None:
    await asyncio.sleep(120)
    while busy():
        await asyncio.sleep(60)
    await asyncio.sleep(90)                      # Bonsai comes back after the build's last render
    Q._log("Barry's 2nd Short: writing now (video 1 is built)")
    open(comfy_image._REEL_MARK, "w").write("Barry's 2nd Short: Ilnora is writing")
    ok = False
    try:
        for attempt in (1, 2, 3):
            ok = await Q.make_one("short", "tonight's videos, Short 2", BARRY)
            Q._log(f"Barry's 2nd Short -> {'queued' if ok else 'missed'} (try {attempt})")
            if ok:
                break
    finally:
        try:
            os.remove(comfy_image._REEL_MARK)
        except OSError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
