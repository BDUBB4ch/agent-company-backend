"""Barry 2026-10-06 ~10:30: "i  need 1 more 2 minute video for today".
Her office's standing Short turn + his words verbatim (nothing from me), up to 3 tries, then built NOW (his "for
today" -- outside the 18:00 window, so this script builds it itself instead of the queue).
Log: data/video_queue/queue.log + data/reels/make_video.log"""
import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import comfy_image  # noqa: E402
import video_queue as Q  # noqa: E402

BARRY = 'FROM BARRY (his words): "i  need 1 more 2 minute video for today"'


async def main() -> None:
    before = {j["_file"] for j in Q._jobs()}
    open(comfy_image._REEL_MARK, "w").write("Barry's video for today: Ilnora is writing")
    ok = False
    try:
        for attempt in (1, 2, 3):
            ok = await Q.make_one("short", "today's video", BARRY)
            Q._log(f"Barry's video for today -> {'queued' if ok else 'missed'} (try {attempt})")
            if ok:
                break
    finally:
        try:
            os.remove(comfy_image._REEL_MARK)
        except OSError:
            pass
    new = [j for j in Q._jobs() if j["_file"] not in before and j.get("status") == "queued"]
    if new:
        Q._log(f"Barry's video for today: building '{new[0]['pkg'].get('title')}' now")
        await Q._build_one(new[0])


if __name__ == "__main__":
    asyncio.run(main())
