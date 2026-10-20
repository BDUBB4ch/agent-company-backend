"""Barry 2026-10-06 ~21:10: "Ok, i want 2 more vids. the first is a short of her introducing herself. and the second.
lets do a longform. new plant or plants, something epic and cool as fuck!"
Her office's standing turn + his words verbatim (nothing from me), up to 3 tries each, flag held while she writes;
then the queue builds them (Short first). The Long is marked rush so it starts even if it runs past 09:00.
Log: data/video_queue/queue.log"""
import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import comfy_image  # noqa: E402
import video_queue as Q  # noqa: E402

ASKS = [("short", 'FROM BARRY (his words): "the first is a short of her introducing herself."'),
        ("long", 'FROM BARRY (his words): "lets do a longform. new plant or plants, something epic and cool as fuck!"')]


async def main() -> None:
    open(comfy_image._REEL_MARK, "w").write("Barry's 2 new videos: Ilnora is writing")
    try:
        for form, words in ASKS:
            before = {j["_file"] for j in Q._jobs()}
            for attempt in (1, 2, 3):
                ok = await Q.make_one(form, f"Barry's new {form}", words, use_plan=False)
                Q._log(f"Barry's new {form} -> {'queued' if ok else 'missed'} (try {attempt})")
                if ok:
                    break
            if form == "long":
                for j in Q._jobs():
                    if j["_file"] not in before and j.get("status") == "queued":
                        j["rush"] = True
                        Q._write(j)
                        Q._log(f"rush set on '{j['pkg'].get('title')}'")
    finally:
        try:
            os.remove(comfy_image._REEL_MARK)
        except OSError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
