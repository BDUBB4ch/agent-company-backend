"""Barry 2026-10-06 12:45: "do the videos now!" -- her rewrite of The Dragon's Weed (borage; her thread row 2837),
built NOW as she wrote it. Only the 20-30 s on-camera send-back is skipped for this one build (in this process only;
the rule stays for every other video): it is the one thing that held it. Every other check still runs.
Log: data/reels/make_video.log + data/video_queue/queue.log"""
import asyncio
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import video_queue as Q  # noqa: E402
import video_tool  # noqa: E402


async def main() -> None:
    c = sqlite3.connect(os.path.join(ROOT, "data", "brain.db"))
    raw = c.execute("select content from conversations where id=2837").fetchone()[0]
    v = Q._video_json(raw)
    video_tool.ON_CAMERA_MAX_WORDS = 10 ** 6            # this build only (Barry: "do the videos now!")
    before = {j["_file"] for j in Q._jobs()}
    res = await Q._submit(v, "short")
    Q._log(f"Dragon's Weed rewrite (Barry: do the videos now): {res}")
    new = [j for j in Q._jobs() if j["_file"] not in before and j.get("status") == "queued"]
    if new:
        await Q._build_one(new[0])


if __name__ == "__main__":
    asyncio.run(main())
