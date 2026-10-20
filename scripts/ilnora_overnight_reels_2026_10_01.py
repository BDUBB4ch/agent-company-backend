"""Ilnora makes two videos overnight (2026-10-01, Barry: "have her start creating a couple of videos, while i sleep").

For each video: ask her (office window, relayed from Barry) for a reel package -- topic and format are HERS -- then
render it with backend/reel_builder.build_reel (local: her locked voice, stills, captions, music -> MP4), and put the
MP4 on Barry's DESK (Out box card with download). Nothing is posted anywhere. If the builder rejects a package
(over 3:00, unnamed plant, ...) she is told why once and sends a fix. Log: data/reels/overnight_2026-10-01.log
"""
import asyncio
import datetime
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import memory  # noqa: E402
import reel_builder  # noqa: E402

LOG = os.path.join(ROOT, "data", "reels", "overnight_2026-10-01.log")

# THE BUILDER'S PLANT CHECK, stated exactly (reel_builder._PLANT_WORDS / _unnamed_plant_scenes). Her first Short
# failed it twice because she was only told "a scene that shows a plant", not which words count.
PLANT_RULE = ("The builder checks this mechanically: if a scene's image_prompt uses ANY of these words -- herb, "
              "herbs, plant, plants, leaf, leaves, flower, flowers, blossom, petal, sprig, weed, seedling, stem, "
              "bud, shrub, bush, vine, root, bark -- that scene must also have \"plant\": \"<scientific name>\" of "
              "the plant you mean, or else rewrite that picture without those words.")
SHAPE = (
    'Write it as a package for your video builder, in one ```json fence, exactly this shape:\n'
    '{"title": "...", "mood": "spooky|calm|upbeat|mystic", "voice_agent": "ilnora", "format": "short|long", '
    '"scenes": [{"narration": "...", "image_prompt": "..."}], "caption": "...", "hashtags": ["#..."]}\n'
    'How the builder works: each scene is one spoken line (about 6 seconds) over one picture. A scene can show you '
    'instead of a picture: {"narration": "...", "show": "self"}. Any scene whose picture shows a plant must name it: '
    'add "plant": "<scientific name>" so the right species is drawn. ' + PLANT_RULE +
    ' "short" = vertical for TikTok and Shorts, at most '
    '3:00 spoken (about 25 scenes). "long" = widescreen YouTube; keep it under about 40 scenes tonight so both videos '
    'finish before morning. Your voice, captions and music are added for you. Reply with only the json.'
)
# Barry, same night: "just do 3 shorts for tonight and we will do 2 regular tomorrow" / "whatever she feels like
# making". Video 1 = the Short she already wrote for the first ask (conversations row 2782); 2 and 3 asked below.
FIRST_REPLY_ROW = 2782
ASKS = [
    "From Barry (relayed by Claude): Barry wants three Shorts from you tonight; your first one is already "
    "building. This is Short 2 of 3: \"format\": \"short\". Pick a different topic from your first one -- whatever "
    "you feel like making. " + SHAPE,
    "From Barry (relayed by Claude): Short 3 of 3 for tonight: \"format\": \"short\". A different topic from your "
    "first two -- whatever you feel like making. " + SHAPE,
]


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
    return pkg


def to_desk(pkg: dict, res: dict) -> int | None:
    """PENDING REVIEW, not auto-approved (Barry, same night: "i need to approve and be able to download").
    action_type social_post: dispatch has no destination for it, so his approve click marks it approved and
    sends nothing anywhere. The MP4 is copied into data/agent_files/ilnora/ because the download endpoint
    only serves files under data/agent_files (agent_files.resolve_download)."""
    import shutil
    import agent_files
    dest_dir = agent_files._agent_dir("ilnora")
    os.makedirs(dest_dir, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9 _-]+", "", pkg.get("title") or "video").strip().replace(" ", "_")[:60] or "video"
    dest = os.path.join(dest_dir, f"{safe}_{os.path.basename(res['video'])}")
    shutil.copy2(res["video"], dest)
    tags = " ".join(pkg.get("hashtags") or [])
    text = (f"VIDEO: {pkg.get('title') or 'untitled'} ({res.get('format')}, {res.get('seconds')} s)\n"
            f"Caption: {pkg.get('caption') or ''}\nHashtags: {tags}\n"
            + (f"Music: {res.get('music_credit')}\n" if res.get("music_credit") else ""))
    return memory.queue_for_approval("ilnora", "social_post", text, file_path=dest)


async def one(n: int, message: str, reply: str | None = None) -> None:
    if reply is None:
        log(f"video {n}: asking Ilnora")
        reply = ask(message)
    else:
        log(f"video {n}: using the package she already wrote")
    pkg = package_of(reply)
    for attempt in range(1, 5):          # her package + up to 3 fixes (was 1 fix; the plant check needed more)
        last = attempt == 4
        if pkg is None:
            log(f"video {n}: no readable package in her reply ({len(reply)} chars)")
            if last:
                return
            reply = ask("From Barry (relayed by Claude): the builder could not read a package in that reply. "
                        "Send it again as one ```json fence, only the json.")
            pkg = package_of(reply)
            continue
        log(f"video {n}: '{pkg.get('title')}' format={pkg.get('format')} scenes={len(pkg.get('scenes') or [])} -- building")
        res = await reel_builder.build_reel(pkg, log=lambda s: log(f"  {s}"))
        if res.get("ok"):
            aid = to_desk(pkg, res)
            log(f"video {n}: DONE {res.get('seconds')} s in {res.get('build_seconds')} s -> {res['video']} (pending review card {aid})")
            return
        log(f"video {n}: builder said: {res.get('why')}")
        if last:
            return
        reply = ask(f"From Barry (relayed by Claude): the video builder could not make that one. It said: "
                    f"{res.get('why')} {PLANT_RULE} Fix the package and send it again as one ```json fence, "
                    f"only the json.")
        pkg = package_of(reply)


async def main() -> None:
    log("=== overnight start (3 shorts, resumed with the exact plant rule) ===")
    # RESUME (2026-10-01): nothing she already wrote is thrown away. Video 1 = her latest fix (row 2784); video 2 =
    # her answer to the Short-2 ask (row 2785), which was still being written when the run was stopped.
    with memory.get_db() as conn:
        first = conn.execute("SELECT content FROM conversations WHERE id = 2784").fetchone()
    second = None
    for _ in range(90):                  # up to 30 min for her in-flight answer to land
        with memory.get_db() as conn:
            row = conn.execute("SELECT content FROM conversations WHERE agent_id = 'ilnora' AND role = 'agent' "
                               "AND id > 2785 ORDER BY id LIMIT 1").fetchone()
        if row:
            second = row[0]
            break
        await asyncio.sleep(20)
    log(f"resume: video 1 from row 2784 ({'found' if first else 'MISSING'}), video 2 "
        f"{'from her landed answer' if second else 'will be asked again'}")
    jobs = [(1, "", first[0] if first else None), (2, ASKS[0], second), (3, ASKS[1], None)]
    for n, message, reply in jobs:
        if n == 1 and reply is None:
            log("video 1: her package is missing -- asking for a fresh Short instead")
            message = ASKS[0]
        try:
            await one(n, message, reply)
        except Exception as e:  # noqa: BLE001 -- one bad video must not cost the others
            log(f"video {n}: FAILED {type(e).__name__}: {e}")
    log("=== overnight end ===")


if __name__ == "__main__":
    asyncio.run(main())
