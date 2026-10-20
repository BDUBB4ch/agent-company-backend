"""Ilnora makes three Shorts HERSELF with make_video, seen through to done (2026-10-01, Barry: "I want her to make her
own video!!!!" / "Get this video shit going first" / "if there are issues, fix it and continue").

Asks her (relayed from Barry); she calls make_video (backend/video_tool.py), which checks his rules and builds in
the background. This watcher reads data/reels/make_video.log: fewer than 3 started -> asks for the rest; a build
FAILED -> tells her why and asks her to remake it; every DONE Short must be 120-180 s. Ends with Bonsai up.
Log: data/reels/make_shorts_2026-10-01.log
"""
import datetime
import json
import os
import re
import subprocess
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL_LOG = os.path.join(ROOT, "data", "reels", "make_video.log")
LOG = os.path.join(ROOT, "data", "reels", "make_shorts_2026-10-01.log")
FLAG = os.path.join(ROOT, "data", "video_rendering.flag")
WANT = 3


def log(msg: str) -> None:
    line = f"{datetime.datetime.now():%H:%M:%S} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def ask(message: str) -> str:
    req = urllib.request.Request("http://127.0.0.1:8420/api/chat",
                                 data=json.dumps({"agent_id": "ilnora", "message": message, "personal": False}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=2400).read()).get("reply", "")


def tool_events(since: str) -> dict:
    """title -> {'state': building|done|failed, 'seconds', 'why', 'card'} from make_video.log since a timestamp."""
    ev: dict = {}
    if not os.path.exists(TOOL_LOG):
        return ev
    for line in open(TOOL_LOG, encoding="utf-8"):
        if line[:19] < since or line.startswith(" ") or line[20:22] == "  ":
            continue
        m = re.search(r"ilnora: building '(.+)' \(", line)
        if m:
            ev[m.group(1)] = {"state": "building"}
        m = re.search(r"ilnora: DONE '(.+)' ([\d.]+) s in .* card (\d+)", line)
        if m:
            ev[m.group(1)] = {"state": "done", "seconds": float(m.group(2)), "card": m.group(3)}
        m = re.search(r"ilnora: FAILED '(.+)': (.*)$", line)
        if m:
            ev[m.group(1)] = {"state": "failed", "why": m.group(2)}
    return ev


def up(port: int, path: str) -> bool:
    try:
        return urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5).status == 200
    except Exception:  # noqa: BLE001
        return False


def main() -> None:
    since = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log("=== Ilnora makes 3 Shorts herself, ONE per ask ===")
    # ONE VIDEO PER ASK (2026-10-01): asked for three at once she planned and wrote scripts out loud until the
    # 6,144-token reply ceiling ("reasoning spilled ... hit the ceiling") and never reached the tool call.
    # TWO TURNS PER VIDEO (2026-10-01): research + script + tool call in ONE turn ran past the 360 s turn ceiling
    # (bonsai_llm.TURN_TIME_CEILING_SECONDS) after her PubMed/web rounds, which forces a no-tools answer, so the
    # make_video call never happened. Turn 1 = topic + research (her words, short). Turn 2 = write it + make_video.
    asks = 0
    for n in range(1, WANT + 1):
        made = [t for t, e in tool_events(since).items() if e["state"] in ("building", "done")]
        r = ask(f"From Barry (relayed by Claude): Short {n} of 3 for today, step 1 of 2. Pick a topic you'd love"
                + (f" (different from {', '.join(made)})" if made else "")
                + " and look into it -- what's true, what's legend, your best hook. Reply in a few lines: the topic "
                  "and your key facts. Don't make the video yet.")
        asks += 1
        log(f"short {n} step 1: {r[:200]!r}")
        for attempt in range(1, 4):
            before = len([t for t, e in tool_events(since).items() if e["state"] in ("building", "done")])
            msg = ("From Barry (relayed by Claude): step 2 of 2 -- make it now. Write the 2 to 3 minute Short from "
                   "what you just found and call your make_video tool with it. Don't write the script out in your "
                   "reply; put it straight into the tool call."
                   if attempt == 1 else
                   "From Barry (relayed by Claude): that wasn't a make_video call, so nothing was made. Call "
                   "make_video now with your script for this Short.")
            r = ask(msg)
            asks += 1
            log(f"short {n} step 2 try {attempt}: {r[:200]!r}")
            time.sleep(5)
            if len([t for t, e in tool_events(since).items() if e["state"] in ("building", "done")]) > before:
                break
    handled_fail: set = set()
    while True:
        ev = tool_events(since)
        good = [t for t, e in ev.items() if e["state"] in ("building", "done")]
        failed = [t for t, e in ev.items() if e["state"] == "failed" and t not in handled_fail]
        for t in failed:
            handled_fail.add(t)
            log(f"FAILED '{t}': {ev[t]['why']} -- asking her to remake it")
            ask(f"From Barry (relayed by Claude): your Short '{t}' did not build. The builder said: {ev[t]['why']} "
                f"Fix it and make it again with make_video.")
            asks += 1
        if len(good) < WANT and not failed and asks < 14:
            log(f"{len(good)} of {WANT} started -- asking for the next one")
            r = ask(f"From Barry (relayed by Claude): {len(good)} of today's 3 Shorts are made"
                    + (f" ({', '.join(good)})" if good else "")
                    + ". Make the next one now: a different topic you'd love, 2 to 3 minutes -- call make_video, "
                      "don't write it out in your reply.")
            log(f"her reply: {r[:200]!r}")
            asks += 1
            continue
        ev = tool_events(since)
        building = [t for t, e in ev.items() if e["state"] == "building"]
        if not building and (len([t for t, e in ev.items() if e["state"] == "done"]) >= WANT or asks >= 14):
            break
        time.sleep(60)
    ev = tool_events(since)
    for t, e in ev.items():
        if e["state"] == "done":
            ok = 120 <= e["seconds"] <= 180
            log(f"{'OK ' if ok else 'LENGTH OFF '} '{t}' {e['seconds']} s -> DESK (download id {e['card']})")
        else:
            log(f"NOT DONE '{t}': {e}")
    if not up(8811, "/health") and not os.path.exists(FLAG):
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "$c = Get-NetTCPConnection -LocalPort 8420 -State Listen -ErrorAction SilentlyContinue; "
                        "if ($c) { Stop-Process -Id $c.OwningProcess -Force }"], capture_output=True, timeout=30)
        for _ in range(36):
            time.sleep(10)
            if up(8811, "/health"):
                break
    log(f"=== end | bonsai {'UP' if up(8811, '/health') else 'NOT UP'} ===")


if __name__ == "__main__":
    main()
