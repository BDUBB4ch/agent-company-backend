"""Her intro Short, again (2026-10-07 ~03:00). Barry's ask reached her as a fragment ("the first is a short of her
introducing herself.") and she drifted to plant videos / a remake twice. Now she gets his WHOLE message, verbatim.
Waits for scripts/two_new_2026_10_06.py (the Long) to finish, restarts the backend once (title-match fix live, after
the queue loop's startup so the writing hold survives), then up to 3 tries; the queue builds it.
Log: data/video_queue/queue.log"""
import asyncio
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import comfy_image  # noqa: E402
import video_queue as Q  # noqa: E402

PY = os.path.join(ROOT, "venv", "Scripts", "python.exe")
BARRY = ('FROM BARRY (his whole message, his words): "I like the videos. One thing i want to correct. I do want her to '
         'show the text for the plants she is talking about on the screen for a couple of seconds. thats it. Ok, i '
         'want 2 more vids. the first is a short of her introducing herself. and the second. lets do a longform. new '
         'plant or plants, something epic and cool as fuck!" -- THIS video is the first one: the Short of you '
         'introducing yourself.')


def running(name: str) -> bool:
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine "
                          f"-match '{name}' }} | Measure-Object).Count"], capture_output=True, text=True).stdout
    return (out.strip() or "0") != "0"


async def main() -> None:
    while running("two_new_2026"):
        await asyncio.sleep(2)
    # the Long (if it queued) waits while she writes the intro -- a build takes Bonsai off the card
    held = []
    for j in Q._jobs():
        if j.get("status") == "queued" and j["pkg"].get("format") == "long":
            j["status"] = "paused"
            Q._write(j)
            held.append(j["_file"])
            Q._log(f"intro Short: holding the Long '{j['pkg'].get('title')}' while she writes")
    Q._log("intro Short: the Long's turn is over -- restarting the backend for the title fix")
    pf = subprocess.run([PY, os.path.join(ROOT, "scripts", "preflight_check.py")], cwd=ROOT, capture_output=True)
    if pf.returncode == 0 and not any(j.get("status") == "building" for j in Q._jobs()):
        n0 = open(Q.LOG, encoding="utf-8").read().count("loop started")
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "$procId=(Get-NetTCPConnection -LocalPort 8420 -State Listen).OwningProcess; "
                        "Stop-Process -Id $procId -Force"])
        for _ in range(120):
            await asyncio.sleep(5)
            if open(Q.LOG, encoding="utf-8").read().count("loop started") > n0:
                break
        await asyncio.sleep(60)
    open(comfy_image._REEL_MARK, "w").write("Barry's intro Short: Ilnora is writing")
    try:
        for attempt in (1, 2, 3):
            ok = await Q.make_one("short", "Barry's intro Short", BARRY, use_plan=False)
            Q._log(f"Barry's intro Short -> {'queued' if ok else 'missed'} (try {attempt})")
            if ok:
                break
    finally:
        try:
            os.remove(comfy_image._REEL_MARK)
        except OSError:
            pass
    # Short first (quicker); then the Long goes back in line, still rush
    if held:
        for _ in range(30):
            if any(j.get("status") == "building" for j in Q._jobs()):
                break
            await asyncio.sleep(10)
        for j in Q._jobs():
            if j["_file"] in held and j.get("status") == "paused":
                j["status"] = "queued"
                j["rush"] = True
                Q._write(j)
                Q._log(f"the Long '{j['pkg'].get('title')}' is back in line (rush)")


if __name__ == "__main__":
    asyncio.run(main())
