"""Barry 2026-10-06 12:46: "you know want them done, get them done!!!!!!" -- after The Dragon's Weed finishes, build her
already-written Short "Halloween's Real Garden" (paused since 10-03) straight away, no writing turn to fail."""
import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import comfy_image  # noqa: E402
import video_queue as Q  # noqa: E402


async def main() -> None:
    await asyncio.sleep(60)
    while comfy_image.reel_building() or any(j.get("status") == "building" for j in Q._jobs()):
        await asyncio.sleep(30)
    job = next((j for j in Q._jobs() if j.get("status") == "paused"
                and j["pkg"].get("title", "").startswith("Halloween's Real Garden")), None)
    if job:
        Q._log("Barry's 2nd video today: building 'Halloween's Real Garden' now")
        await Q._build_one(job)


if __name__ == "__main__":
    asyncio.run(main())
