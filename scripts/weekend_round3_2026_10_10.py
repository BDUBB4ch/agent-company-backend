"""Round 3 of Barry's weekend ask (2026-10-10). Builds are HELD (the running build finishes). When it has:
restart the backend (preflight first) so the delegate_to roster fix + JSON tool-call parser load, then Ilnora's
finishing turns on her Long ("The Sacred Thornapple" -- one check left: a part shows Atropa belladonna, already in
"Halloween's Real Garden"), then Barry's ask to Elliot again (his words; Elliot could not see Ilnora as a teammate),
then Sophie's training brief, then release builds. Log: data/video_queue/weekend_2026-10-10.log"""
import asyncio
import datetime
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import httpx  # noqa: E402
import video_queue as vq  # noqa: E402

LOG = os.path.join(ROOT, "data", "video_queue", "weekend_2026-10-10.log")
PY = os.path.join(ROOT, "venv", "Scripts", "python.exe")


def log(m: str) -> None:
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} round3: {m}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def building() -> list:
    return [j["pkg"].get("title") for j in vq._jobs() if j.get("status") == "building"]


def ping() -> dict:
    try:
        return httpx.get("http://127.0.0.1:8420/api/ping", timeout=5).json()
    except Exception:  # noqa: BLE001
        return {}


def restart() -> bool:
    pf = subprocess.run([PY, os.path.join(ROOT, "scripts", "preflight_check.py")], cwd=ROOT,
                        capture_output=True, text=True)
    if pf.returncode != 0:
        log("preflight FAILED -- not restarting:\n" + pf.stdout[-800:])
        return False
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "$procId=(Get-NetTCPConnection -LocalPort 8420 -State Listen).OwningProcess; "
                    "Stop-Process -Id $procId -Force"], capture_output=True)
    for _ in range(36):
        time.sleep(10)
        if ping().get("ok"):
            log("backend restarted and answering")
            time.sleep(20)
            return True
    log("backend did not come back in 6 min")
    return False


def chat(agent: str, msg: str, task: bool) -> str:
    try:
        r = httpx.post("http://127.0.0.1:8420/api/chat", json={"agent_id": agent, "message": msg, "task": task,
                                                               "personal": False}, timeout=2400)
        return f"HTTP {r.status_code}, {len((r.json() or {}).get('reply') or '') if r.status_code == 200 else r.text[:200]}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR {type(e).__name__}: {e}"


async def main() -> None:
    vq.hold_builds(240, why="round 3: restart + Long finish + Elliot/Sophie (Claude)")
    t0 = time.time()
    while building() and time.time() - t0 < 4 * 3600:
        time.sleep(60)
    log(f"no build running (waited {int((time.time() - t0) / 60)} min)")
    vq.hold_builds(240, why="round 3 (Claude)")
    if not restart():
        vq.release_builds()
        return
    vq.hold_builds(240, why="round 3 (Claude)")
    before = vq.queued_titles()
    try:
        ok = await vq.write_long_draft("Barry's weekend ask, the Long (finish)",
                                       ask="Barry: \"at lease 1 long form done perfectly\"")
    except Exception as e:  # noqa: BLE001
        ok = False
        log(f"Long finish ERROR {type(e).__name__}: {e}")
    log(f"Long: {'QUEUED ' + repr([t for t in vq.queued_titles() if t not in before]) if ok else 'NOT queued'}")
    log("Elliot: " + chat("movie", "i need you to go meet Ilnora. She will need your help, maybe with some of her "
                                   "work. just ask her", False))
    brief = os.path.join(ROOT, "data", "sophie_brief_2026-10-10.sent.md")
    log("Sophie brief: " + chat("engineer", open(brief, encoding="utf-8").read(), True))
    vq.release_builds()
    log("builds released")


if __name__ == "__main__":
    asyncio.run(main())
