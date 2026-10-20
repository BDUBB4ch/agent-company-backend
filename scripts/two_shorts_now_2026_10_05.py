"""Barry 2026-10-05 21:20: "i need 2 more 2 min videos right now" / "no redos, all new videos".
1. Holds reel_building.flag while she writes, so the queue cannot start a build (unload Bonsai) mid-writing.
2. Ilnora writes 2 NEW full 2-minute Shorts (make_one; up to 2 tries each), they queue.
3. Releases the flag -> the queue builds them now (window open), oldest first.

Log: data/video_queue/queue.log (+ prints)."""
import asyncio
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import comfy_image  # noqa: E402
import video_queue as Q  # noqa: E402

# Barry 21:40: "I dont want you telling her what type of video top make, so remover your commands" -- no note
# from me; she gets only the office's standing video turn + Barry's own words, verbatim.
BARRY = 'FROM BARRY (his words): "ok, i need 2 good ass production style minutes of 2 different plants"'


def files() -> set[str]:
    return {f for f in os.listdir(Q.QDIR) if f.startswith("job_") and f.endswith(".json")}


async def main() -> None:
    before = files()
    open(comfy_image._REEL_MARK, "w").write("Barry's 2 Shorts: Ilnora is writing")
    try:
        for k in (1, 2):
            for attempt in (1, 2):
                ok = await Q.make_one("short", f"tonight's videos, Short {k}", BARRY)
                # 2026-10-05 23:40 MEASURED: her make_video calls get the office's send-backs (on-camera words, length),
                # she says "let me fix" and the turn ends -- so she gets plain go-on turns to land the fix, instead of
                # a fresh start that throws her work away (office mechanics, no words about the video itself)
                for _ in range(3):
                    if ok:
                        break
                    before = len(Q.queued())
                    await Q._ask("Go on -- finish the fix and send the corrected video now with make_video.")
                    ok = len(Q.queued()) > before
                Q._log(f"Barry's 2 new Shorts: {k} of 2 -> {'queued' if ok else 'missed'} (try {attempt})")
                if ok:
                    break
    finally:
        try:
            os.remove(comfy_image._REEL_MARK)
        except OSError:
            pass
    new = sorted(files() - before)
    Q._log("Barry's 2 new Shorts queued (the queue builds them now): " + ", ".join(new))


if __name__ == "__main__":
    asyncio.run(main())
