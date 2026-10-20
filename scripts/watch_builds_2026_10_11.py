"""Wake Claude when one of Ilnora's builds finishes or fails, or when a build stalls (make_video.log silent 60 min)."""
import os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import video_queue as vq
LOG = os.path.join(ROOT, "data", "reels", "make_video.log")
def state():
    return {j["pkg"].get("title"): j.get("status") for j in vq._jobs() if j.get("status") in ("queued", "building", "failed")
            or (j.get("finished") or "") >= "2026-10-11"}
start, t0 = state(), time.time()
while time.time() - t0 < 14 * 3600:
    time.sleep(120)
    now = state()
    changed = {t: (start.get(t), s) for t, s in now.items() if start.get(t) != s and s in ("done", "failed")}
    if changed:
        print("FINISHED:", changed); break
    if any(s == "building" for s in now.values()) and time.time() - os.path.getmtime(LOG) > 3600:
        print("STALL: make_video.log silent for 60+ min"); break
print("state:", state())
