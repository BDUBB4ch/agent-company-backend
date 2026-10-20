"""Round 4 (2026-10-10/11). The Long "The Sacred Thornapple" turned out to be a REMAKE: Datura wrightii is the subject
of "The Flower That Walks Between Worlds" (made 10-09) -- her week plan (written 18:25 by the old schedule, now off)
still told her to make it. Wait for the running build, restart (checker: names the part for a used plant; lists every
repeated part at once), archive the remake draft and the stale plan, then a brand-new Long; then release builds."""
import asyncio, datetime, os, shutil, subprocess, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts")); sys.path.insert(0, os.path.join(ROOT, "backend"))
import weekend_round3_2026_10_10 as r3  # noqa: E402  (log, building, restart helpers)
import video_queue as vq  # noqa: E402
import video_tool  # noqa: E402


def log(m):
    r3.log("round4: " + m)


async def main():
    vq.hold_builds(240, why="round 4: restart + a new Long (Claude)")
    t0 = time.time()
    while r3.building() and time.time() - t0 < 5 * 3600:
        time.sleep(60)
    log(f"no build running (waited {int((time.time() - t0) / 60)} min)")
    vq.hold_builds(240, why="round 4 (Claude)")
    if not r3.restart():
        vq.release_builds(); return
    vq.hold_builds(240, why="round 4 (Claude)")
    if video_tool.load_draft("ilnora"):
        video_tool._archive_draft("ilnora", "remake -- Datura wrightii is in The Flower That Walks Between Worlds (10-09)")
        log("archived the Sacred Thornapple draft (remake)")
    plan = os.path.join(vq.QDIR, "plan.md")
    if os.path.exists(plan):
        shutil.move(plan, os.path.join(vq.QDIR, f"plan_archived_{datetime.datetime.now():%Y-%m-%d_%H%M}.md"))
        log("archived the stale week plan (it named the remake)")
    before = vq.queued_titles()
    for attempt in (1, 2):
        try:
            ok = await vq.write_long_draft(f"Barry's weekend ask, the Long (new{', try 2' if attempt == 2 else ''})")
        except Exception as e:  # noqa: BLE001
            ok = False; log(f"Long ERROR {type(e).__name__}: {e}")
        new = [t for t in vq.queued_titles() if t not in before]
        log(f"Long attempt {attempt}: {'QUEUED ' + repr(new) if new else 'NOT queued'}")
        if new:
            break
        d = video_tool.load_draft("ilnora")
        if d:
            res = await video_tool.draft("ilnora", {"action": "check"})
            log(f"  draft '{d.get('title')}' {len(d.get('parts') or [])} parts; check: {str(res.get('fix_this'))[:300]}")
    vq.release_builds()
    log("builds released")

if __name__ == "__main__":
    asyncio.run(main())
