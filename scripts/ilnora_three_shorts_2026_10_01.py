"""Ilnora's three Shorts -- seen through to done (2026-10-01). Barry: "I want her to make her own video!!!!",
"see this through, dont ask me shit", "if there are issues, fix it and continue".

What failed before (scripts/ilnora_make_shorts_2026_10_01.py): asking her to call make_video with a whole 2-3 minute
script made her turns run 15+ minutes (4,500-token rounds at ~16 tok/s) until the 300 s request timeout / 360 s turn
ceiling, then the 9b fallback wrote junk and stopped Bonsai. Every time she was asked to WRITE the video out in her
reply, she did it well. So:

  turn 1 -- she picks the topic and researches it (short reply)
  turn 2 -- she writes the whole video herself in her reply: title, mood, her parts (what she says + what's on
            screen, as few or as many as she likes), caption, hashtags -- no more research
  then her video goes through make_video's own code (backend/video_tool.py): the SAME rule checks (2-3 min, no
  "Come closer", no "darling", no cannabis, no repeat, plants named) -- any failure goes back to her with the reason
  (her words are never edited) -- and the SAME build + DESK delivery with a download button.
Ends with every Short verified 120-180 s and Bonsai up. Log: data/reels/three_shorts_2026-10-01.log
"""
import asyncio
import datetime
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import memory  # noqa: E402
import video_tool  # noqa: E402

LOG = os.path.join(ROOT, "data", "reels", "three_shorts_2026-10-01.log")
FLAG = os.path.join(ROOT, "data", "video_rendering.flag")
WANT = 3
SHAPE = ('Reply with only your video, as one ```json fence: {"title": "...", "format": "short", "mood": '
         '"spooky|calm|upbeat|mystic", "parts": [{"say": "what you say", "show": "me, or describe the picture", '
         '"plant": "scientific name, only when the picture shows a plant"}], "caption": "...", "hashtags": ["#..."]}. '
         'As few or as many parts as you like.')


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


def video_of(reply: str) -> dict | None:
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", reply, re.S) or re.search(r"(\{.*\})", reply, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def up(port: int, path: str) -> bool:
    try:
        return urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5).status == 200
    except Exception:  # noqa: BLE001
        return False


def bonsai_up() -> None:
    if up(8811, "/health") or os.path.exists(FLAG):
        return
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "$c = Get-NetTCPConnection -LocalPort 8420 -State Listen -ErrorAction SilentlyContinue; "
                    "if ($c) { Stop-Process -Id $c.OwningProcess -Force }"], capture_output=True, timeout=30)
    for _ in range(36):
        time.sleep(10)
        if up(8811, "/health") and up(8420, "/api/agents"):
            return


async def one(n: int, made: list[str], have_research: bool) -> dict | None:
    if not have_research:
        bonsai_up()
        r = ask(f"From Barry (relayed by Claude): Short {n} of 3 for today, step 1 of 2. Pick a topic you'd love"
                + (f" (different from {', '.join(made)})" if made else "")
                + " and look into it -- what's true, what's legend, your best hook. Reply in a few lines: the topic "
                  "and your key facts. Don't make the video yet.")
        log(f"short {n} research: {r[:160]!r}")
    msg = ("From Barry (relayed by Claude): step 2 of 2 -- write the whole 2 to 3 minute Short now from what you "
           "found. No more research. " + SHAPE)
    for rnd in range(1, 6):
        bonsai_up()
        r = ask(msg)
        a = video_of(r)
        if a is None:
            why = "I couldn't read a video in that reply."
        else:
            a["format"] = "short"
            pkg, why = video_tool.check("ilnora", a)
            if pkg is not None:
                words = sum(len(s["narration"].split()) for s in pkg["scenes"])
                log(f"short {n}: '{pkg['title']}' {len(pkg['scenes'])} parts, {words} words -- building")
                video_tool._queued.append(pkg["title"])
                await video_tool._build("ilnora", pkg)
                return pkg
        log(f"short {n} round {rnd}: sent back -- {why[:160]}")
        msg = f"From Barry (relayed by Claude): {why} Fix it. {SHAPE}"
    return None


def done_rows(since: str) -> list[tuple]:
    with memory.get_db() as conn:
        return conn.execute("SELECT id, content, file_path FROM approvals WHERE agent_id='ilnora' AND "
                            "action_type='file' AND content LIKE 'VIDEO: %' AND created_at >= ? ORDER BY id",
                            (since,)).fetchall()


async def main() -> None:
    since = datetime.datetime.now(datetime.timezone.utc).isoformat()
    log("=== Ilnora's 3 Shorts: research turn, then she writes it, then make_video's checks + build ===")
    with memory.get_db() as conn:     # her wormwood research from the run before is still in her thread
        have = conn.execute("SELECT COUNT(*) FROM conversations WHERE agent_id='ilnora' AND role='agent'").fetchone()[0]
    made: list[str] = []
    n = 0
    tries = 0
    while len(made) < WANT and tries < WANT + 2:
        n += 1
        tries += 1
        try:
            pkg = await one(len(made) + 1, made, have_research=(n == 1 and have > 0))
        except Exception as e:  # noqa: BLE001
            log(f"short {len(made) + 1}: FAILED {type(e).__name__}: {e}")
            pkg = None
        rows = done_rows(since)
        if pkg and any(pkg["title"] in r[1] for r in rows):
            made.append(pkg["title"])
            log(f"short {len(made)} DONE: '{pkg['title']}'")
        elif pkg:
            log(f"'{pkg['title']}' did not reach the DESK (see make_video.log) -- trying another")
    for rid, content, path in done_rows(since):
        m = re.search(r"\(short, ([\d.]+) s\)", content)
        secs = float(m.group(1)) if m else -1
        log(f"{'OK' if 120 <= secs <= 180 else 'LENGTH OFF'} {content.splitlines()[0]} -> DESK download id {rid}")
    bonsai_up()
    log(f"=== end: {len(made)}/{WANT} Shorts on the DESK | bonsai {'UP' if up(8811, '/health') else 'NOT UP'} ===")


if __name__ == "__main__":
    asyncio.run(main())
