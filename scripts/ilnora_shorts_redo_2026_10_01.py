"""Ilnora's 3 Shorts, done right (2026-10-01 morning). Barry: "Bitch when i say do something, that means see it
through!!!!!!!!" -- the overnight run (ilnora_overnight_reels_2026_10_01.py) built a duplicate (523 = 524, same
script) and all three opened "Come closer, dear." after he had said a stock opener is weird.

Same pipeline (ask her -> reel_builder.build_reel -> MP4 in data/agent_files/ilnora -> Pending Review card), plus
CHECKS BEFORE ANY CARD TIME, each sent back to her with the reason (her words are never edited):
  * opener: the first line must not start with "Come closer" (Barry: "i dont want her saying Come closer on every
    intro, thats weird... she can say hello, or hi, or introduce herself and the topic in a captive way")
  * repeat: a topic (title or named plant) already used in this run is sent back for a different one
  * the builder's own plant rule, stated exactly
Up to 4 fix rounds per video; it keeps going until 3 distinct Shorts exist or a video runs out of rounds.
Log: data/reels/redo_2026-10-01.log
"""
import asyncio
import datetime
import json
import os
import re
import shutil
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import agent_files  # noqa: E402
import memory  # noqa: E402
import reel_builder  # noqa: E402

LOG = os.path.join(ROOT, "data", "reels", "redo_2026-10-01.log")
WANT = 3
PLANT_RULE = ("The builder checks this mechanically: if a scene's image_prompt uses ANY of these words -- herb, "
              "herbs, plant, plants, leaf, leaves, flower, flowers, blossom, petal, sprig, weed, seedling, stem, "
              "bud, shrub, bush, vine, root, bark -- that scene must also have \"plant\": \"<scientific name>\" of "
              "the plant you mean, or else rewrite that picture without those words.")
OPENER_RULE = ("Barry does not want \"Come closer\" as your opener. Open however feels alive: hi, hello, your name "
               "and the topic -- grab people in the first seconds your own way.")
SHAPE = (
    'Write it as a package for your video builder, in one ```json fence, exactly this shape:\n'
    '{"title": "...", "mood": "spooky|calm|upbeat|mystic", "voice_agent": "ilnora", "format": "short", '
    '"scenes": [{"narration": "...", "image_prompt": "..."}], "caption": "...", "hashtags": ["#..."]}\n'
    'Each scene is one spoken line (about 6 seconds) over one picture. A scene can show you instead of a picture: '
    '{"narration": "...", "show": "self"}. Any scene whose picture shows a plant must name it: add "plant": '
    '"<scientific name>". ' + PLANT_RULE + ' ' + OPENER_RULE + ' LENGTH: Barry wants each Short 2 to 3 minutes '
    'long. Your voice speaks about 2.3 words a second, so that is 300 to 400 words of narration in total -- about '
    '20 to 30 scenes. Under 290 or over 410 words gets sent back. Plant pictures take about 10 minutes each to draw, '
    'other pictures about 1.5 minutes. Your voice, captions and music are added for you. Reply with only the json.'
)
# Barry 2026-10-01: "they are supposed to be 2-3 minutes, not seconds". Measured on the built reels: her locked
# voice runs 2.21-2.63 words/s including pauses -> 120-180 s = ~290-410 words. Checked BEFORE any card time.
MIN_WORDS, MAX_WORDS = 290, 410


def log(msg: str) -> None:
    line = f"{datetime.datetime.now():%H:%M:%S} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def ask(message: str) -> str:
    req = urllib.request.Request("http://127.0.0.1:8420/api/chat",
                                 data=json.dumps({"agent_id": "ilnora", "message": message,
                                                  "personal": False}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=1800).read()).get("reply", "")


def package_of(reply: str) -> dict | None:
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", reply, re.S) or re.search(r"(\{.*\})", reply, re.S)
    if not m:
        return None
    try:
        pkg = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    pkg["voice_agent"] = "ilnora"
    pkg["format"] = "short"
    return pkg


def topic_keys(pkg: dict) -> set[str]:
    keys = {re.sub(r"[^a-z ]", "", (pkg.get("title") or "").lower()).strip()}
    keys |= {" ".join(str(s.get("plant") or "").lower().split()) for s in pkg.get("scenes") or [] if s.get("plant")}
    return {k for k in keys if k}


def problems(pkg: dict, used: set[str]) -> str:
    scenes = pkg.get("scenes") or []
    first = (scenes[0].get("narration") or "").strip().lower() if scenes else ""
    if first.startswith("come closer"):
        return "Your first line opens with \"Come closer\". " + OPENER_RULE
    spoken = " ".join((s.get("narration") or "") for s in scenes) + " " + (pkg.get("caption") or "")
    # Barry 2026-09-24: "I dont like the Darling word she uses"
    if re.search(r"\bdarling\b", spoken, re.I):
        return "Barry doesn't want the word \"darling\" in your videos. Say it your own way without it."
    # Barry 2026-09-24 channel plan: no cannabis on her page (he runs a separate cannabis channel)
    if re.search(r"\b(cannabis|marijuana|thc|cbd|hemp)\b", spoken + " " + " ".join(pkg.get("hashtags") or []), re.I):
        return ("No cannabis on your channel -- Barry runs a separate one. Pick a different plant or take that "
                "part out.")
    words = sum(len((s.get("narration") or "").split()) for s in scenes)
    if not MIN_WORDS <= words <= MAX_WORDS:
        return (f"That is {words} words of narration -- about {words / 2.3:.0f} seconds. Barry wants 2 to 3 minutes: "
                f"{MIN_WORDS} to {MAX_WORDS} words in total, about 20 to 30 scenes. "
                + ("Make it longer." if words < MIN_WORDS else "Trim it."))
    if topic_keys(pkg) & used:
        return (f"That topic is already one of tonight's Shorts ({', '.join(sorted(topic_keys(pkg) & used))}). "
                "Pick a different topic -- whatever you feel like making.")
    return ""


def to_review(pkg: dict, res: dict) -> int | None:
    d = agent_files._agent_dir("ilnora")
    os.makedirs(d, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9 _-]+", "", pkg.get("title") or "video").strip().replace(" ", "_")[:60] or "video"
    dest = os.path.join(d, f"{safe}_{os.path.basename(res['video'])}")
    shutil.copy2(res["video"], dest)
    text = (f"VIDEO: {pkg.get('title') or 'untitled'} (short, {res.get('seconds')} s)\n"
            f"Caption: {pkg.get('caption') or ''}\nHashtags: {' '.join(pkg.get('hashtags') or [])}\n"
            + (f"Music: {res.get('music_credit')}\n" if res.get("music_credit") else ""))
    return memory.queue_for_approval("ilnora", "social_post", text, file_path=dest)


async def one(n: int, used: set[str], reply: str | None = None) -> bool:
    msg = (f"From Barry (relayed by Claude): Barry wants three Shorts from you today, each a different topic -- "
           f"whatever you feel like making. This is Short {n} of 3."
           + (f" Already made today: {', '.join(sorted(used))}; pick something else." if used else "") + " " + SHAPE)
    if reply is None:
        log(f"short {n}: asking Ilnora")
        reply = ask(msg)
    else:
        log(f"short {n}: using the answer she wrote to the paused run's ask (still checked)")
    for rnd in range(1, 6):
        pkg = package_of(reply)
        if pkg is None:
            why = "the builder could not read a package in that reply."
        else:
            why = problems(pkg, used)
            if not why:
                log(f"short {n}: '{pkg.get('title')}' scenes={len(pkg.get('scenes') or [])} -- building")
                res = await reel_builder.build_reel(pkg, log=lambda s: log(f"  {s}"))
                if res.get("ok"):
                    aid = to_review(pkg, res)
                    used |= topic_keys(pkg)
                    log(f"short {n}: DONE '{pkg.get('title')}' {res.get('seconds')} s in {res.get('build_seconds')} s"
                        f" -> pending review card {aid}")
                    return True
                why = f"the video builder could not make it: {res.get('why')} {PLANT_RULE}"
        log(f"short {n}: sent back (round {rnd}): {why[:160]}")
        if rnd == 5:
            return False
        reply = ask(f"From Barry (relayed by Claude): {why} Fix it and send the package again as one ```json "
                    f"fence, only the json.")
    return False


async def main() -> None:
    log("=== redo: 3 Shorts with opener + repeat checks ===")
    used: set[str] = set()
    made = 0
    # the paused first run already asked "Short 1 of 3" -- wait for that answer instead of asking twice
    first = None
    with memory.get_db() as conn:
        q = conn.execute("SELECT id FROM conversations WHERE agent_id='ilnora' AND role='user' AND "
                         "content LIKE '%This is Short 1 of 3%' ORDER BY id DESC LIMIT 1").fetchone()
    if q:
        for _ in range(120):                         # up to 40 min (her bio answer is ahead of it)
            with memory.get_db() as conn:
                row = conn.execute("SELECT content FROM conversations WHERE agent_id='ilnora' AND role='agent' "
                                   "AND id > ? ORDER BY id LIMIT 1", (q[0],)).fetchone()
            if row:
                first = row[0]
                break
            await asyncio.sleep(20)
    for n in range(1, WANT + 1):
        try:
            made += await one(n, used, first if n == 1 else None)
        except Exception as e:  # noqa: BLE001
            log(f"short {n}: FAILED {type(e).__name__}: {e}")
    log(f"=== redo end: {made}/{WANT} Shorts on Pending Review ===")
    # BONSAI BACK UP AT THE END (Barry 2026-09-30: "once, training is over, clean up and make sure bonsai is
    # running"). Renders leave llama-server stopped; a backend restart (watchdog revives it) runs the boot prewarm,
    # which starts Bonsai. Never while a render flag is up.
    import subprocess
    import time
    flag = os.path.join(ROOT, "data", "video_rendering.flag")

    def up(port: int, path: str) -> bool:
        try:
            return urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5).status == 200
        except Exception:  # noqa: BLE001
            return False
    if not up(8811, "/health") and not os.path.exists(flag):
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "$c = Get-NetTCPConnection -LocalPort 8420 -State Listen -ErrorAction SilentlyContinue; "
                        "if ($c) { Stop-Process -Id $c.OwningProcess -Force }"], capture_output=True, timeout=30)
        for _ in range(36):
            time.sleep(10)
            if up(8811, "/health"):
                break
    log(f"bonsai {'UP' if up(8811, '/health') else 'NOT UP'} | backend {'UP' if up(8420, '/api/agents') else 'NOT UP'}")


if __name__ == "__main__":
    asyncio.run(main())
