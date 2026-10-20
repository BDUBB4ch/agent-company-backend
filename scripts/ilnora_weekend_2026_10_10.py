r"""Barry, Saturday 2026-10-10 ~14:45, leaving till Sunday night: "Ilnora needs to have at least 4 shorts done
perfectly and at lease 1 long form done perfectly" / "Ilnora goes as soon as you get everything right. she is off
schedule now" / "Take sophie with you and let her know whats going on. this is training for her."

Runs her WRITING turns through the office's own path (video_queue.make_one / write_long -> /api/chat), with builds
HELD so no build evicts Bonsai under a writing turn; then briefs Sophie; then releases builds. The backend's queue
loop builds them back to back (video_build_window = "any"). Log: data/video_queue/weekend_2026-10-10.log"""
import asyncio
import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import httpx  # noqa: E402
import video_queue as vq  # noqa: E402

LOG = os.path.join(ROOT, "data", "video_queue", "weekend_2026-10-10.log")
SHORTS = int(sys.argv[1]) if len(sys.argv) > 1 else 4
DO_LONG = (sys.argv[2] if len(sys.argv) > 2 else "long") == "long"


def log(m: str) -> None:
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {m}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


async def main() -> None:
    made = []
    for i in range(1, SHORTS + 1):
        vq.hold_builds(120, why="weekend writing turns (Claude)")
        label = f"Barry's weekend ask, Short {i} of {SHORTS}"
        before = vq.queued_titles()
        try:
            ok = await vq.make_one("short", label, use_plan=False)
        except Exception as e:  # noqa: BLE001
            ok = False
            log(f"{label}: ERROR {type(e).__name__}: {e}")
        new = [t for t in vq.queued_titles() if t not in before]
        log(f"{label}: {'QUEUED ' + repr(new) if ok else 'NOT queued'}")
        made += new
    if DO_LONG:
        vq.hold_builds(240, why="weekend Long writing (Claude)")
        before = vq.queued_titles()
        try:
            ok = await vq.write_long("Barry's weekend ask, the Long", ask="Barry: \"at lease 1 long form done perfectly\"")
        except Exception as e:  # noqa: BLE001
            ok = False
            log(f"Long: ERROR {type(e).__name__}: {e}")
        new = [t for t in vq.queued_titles() if t not in before]
        log(f"Long: {'QUEUED ' + repr(new) if ok else 'NOT queued'}")
        made += new
    brief = os.path.join(ROOT, "data", "sophie_brief_2026-10-10.md")
    if os.path.exists(brief):
        vq.hold_builds(30, why="Sophie's training brief (Claude)")
        try:
            async with httpx.AsyncClient(timeout=2400) as cx:
                r = await cx.post("http://127.0.0.1:8420/api/chat", json={
                    "agent_id": "engineer", "message": open(brief, encoding="utf-8").read(), "task": True,
                    "personal": False, "activity": "training with Claude"})
            log(f"Sophie brief: HTTP {r.status_code}, reply {len((r.json() or {}).get('reply') or '')} chars")
        except Exception as e:  # noqa: BLE001
            log(f"Sophie brief: ERROR {type(e).__name__}: {e}")
    vq.release_builds()
    log(f"DONE writing. Queued this run: {made}. Builds released.")


if __name__ == "__main__":
    asyncio.run(main())
