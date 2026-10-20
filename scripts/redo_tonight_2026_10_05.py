"""Detached, 2026-10-05 (Barry 03:50 "stop it now and fix it" / "going to bed. take care of it").
The backdrop fix is tested; the redo of her parts of "Herb Histories & Science" needs ~8 h of card, and builds run only in
her window (Mon-Fri 18:00 -> 09:00, Barry: "the rest of the office needs to be able to work too"). So:
1. wait until 17:59:30 (the redo's reel mark goes up before the queue's 18:00 tick; the queue now waits for it)
2. run scripts/redo_her_parts.py data/reels/20261004_000040 (her shots cached in redo_shots.json)
3. if no Long is queued by then, ask her for one and mark it rush (the 2026-10-04 chain's last step)
Log: data/reels/20261004_000040/redo_tonight.log"""
import datetime
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, "venv", "Scripts", "python.exe")
LOG = os.path.join(ROOT, "data", "reels", "20261004_000040", "redo_tonight.log")


def log(m: str) -> None:
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {m}\n")


def main() -> None:
    start = datetime.datetime.combine(datetime.date(2026, 10, 5), datetime.time(17, 59, 30))
    log(f"waiting for {start:%H:%M:%S}")
    while datetime.datetime.now() < start:
        time.sleep(20)
    log("redoing her parts of Herb Histories & Science")
    r = subprocess.run([PY, os.path.join(ROOT, "scripts", "redo_her_parts.py"), "data/reels/20261004_000040"], cwd=ROOT)
    log(f"redo exited {r.returncode} -- see redo.log")
    code = ("import asyncio, sys, json, glob, os; sys.path.insert(0, 'backend'); os.chdir('backend'); import video_queue as Q\n"
            "async def m():\n"
            "    longs = [j for j in Q.queued() if j['pkg'].get('format') == 'long']\n"
            "    if longs:\n"
            "        Q._log('rush Long: one is already queued -- ' + longs[0]['pkg'].get('title', '')); return\n"
            "    ok = await Q.make_one('long', 'Barry wants uploads: one Long tonight')\n"
            "    Q._log('rush Long: ' + ('queued' if ok else 'missed'))\n"
            "    for f in sorted(glob.glob(os.path.join(Q.QDIR, 'job_*.json')))[::-1]:\n"
            "        j = json.load(open(f, encoding='utf-8'))\n"
            "        if j['status'] == 'queued' and j['pkg'].get('format') == 'long':\n"
            "            j['rush'] = True; json.dump(j, open(f, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)\n"
            "            Q._log('rush set on ' + j['pkg'].get('title', '')); break\n"
            "asyncio.run(m())\n")
    subprocess.run([PY, "-c", code], cwd=ROOT)
    log("done")


if __name__ == "__main__":
    main()
