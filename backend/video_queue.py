"""ILNORA'S VIDEO WEEK -- the queue, the render windows and her schedule (2026-10-03).

Barry, 2026-10-02/03: "she has to direct her own video, prompt it right, each scene should be curated and the videos
can be shorts length and long form. at least 2 longs a week and 2-3 shorts a day" / "over night, 10 mins is ok.
Saturday she can use as planning the next vids, but sunday is when we can get a bunch of videos done. i can be off
the computer and let her get it" / "i want this to be easy" / "your renders and Elliot's always go first" -> "go on all".

QUEUE: make_video no longer builds on the spot -- the checked package is saved to data/video_queue/ (survives
restarts) and built in a RENDER WINDOW, oldest first, one at a time, delivered to his DESK by video_tool._build
exactly as before. A build never starts if its estimate runs past the window (no 9-hour Long eating a workday).
    window: EVERY DAY 18:00 -> 09:00 next morning, nothing in the daytime (Barry 2026-10-07: "her time slot after 6").
While she builds, data/reel_building.flag is up and her calls carry comfy_image.REEL_ACTIVE: Barry's, Elliot's and
MyStudio's renders go first (comfy_image.reel_wait_turn / _wait_out_reel_step).

SCHEDULE (2026-10-07, Barry: "sunday was her planning day. she plans out the next 5 videos. i want to generate after
hours every day" / "she can make a video or 2 sunday as well after planning" / "2-3 still a day" / deep dives weekly /
the redos: "add 1 of those videos in a week, not only do those. just add it in"). Her writing turns go through her
own seat; the office tells her what is due and hands her her own plan -- the topics, words and shots are hers:
    Sunday 18:00     plan her next 5 videos (one is that week's REDO from data/video_queue/redo/docket.json),
                     then 1-2 Shorts
    Mon-Fri 18:00    2-3 Shorts (card budget below); when 5 videos have been made since the plan, she plans the next 5
    Saturday 18:00   the week's Long (deep dive) -- a Long night has no room for Shorts
    "video_shorts_per_day" (live setting) caps a night; a backlog of 3+ unbuilt Shorts makes it 2, 6+ skips the night.
Live switch: setting "video_cadence" = "off" stops her writing turns (the queue still drains). Log:
data/video_queue/queue.log.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import os
import re
import shutil
import time

import httpx

import memory

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QDIR = os.path.join(_ROOT, "data", "video_queue")
LOG = os.path.join(QDIR, "queue.log")
PLAN = os.path.join(QDIR, "plan.md")
# BARRY'S NOTE (2026-10-03, "but halloween is coming, she needs the decor and everything"): data/video_queue/
# office_note.md is read fresh every turn and put in front of her as HIS words. Edit or delete it any time.
NOTE = os.path.join(QDIR, "office_note.md")
FOLDER = os.path.join(os.path.expanduser("~"), "Desktop", "Ilnora's Videos")   # every finished video, for Barry
STATE = os.path.join(QDIR, "state.json")
AGENT = "ilnora"
CHECK_EVERY_S = 60
SLOT_GRACE_H = 3                      # a slot missed by a restart still runs within 3 h of its time
SHORTS_BUDGET_NIGHT = 480             # estimated card minutes, Mon-Fri: 2-3 full Shorts (estimates run 1.1-1.7x short)
SHORTS_BUDGET_SUNDAY = 240            # Sunday after planning: 1-2 Shorts
MAX_SHORTS_PER_DAY = 3                 # Barry: "2-3 still a day"
LONG_NIGHT = 5                         # Saturday: the week's deep dive
PLAN_SIZE = 5                          # Barry: "she plans out the next 5 videos"
REDO_DIR = os.path.join(QDIR, "redo")
DOCKET = os.path.join(REDO_DIR, "docket.json")
LONG_MINUTES = 8                      # Barry 2026-10-14: "longs i want at least 8 minutes" (7 at the least -- video_tool)

# (weekday Mon=0, hour, what) -- all after hours (18:00), so the rest of the office keeps Bonsai all day; the plan
# runs before Sunday's videos (same tick, SLOTS order)
SLOTS = [(6, 18, "plan")] + [(d, 18, "daily") for d in range(7)]


def _log(msg: str) -> None:
    os.makedirs(QDIR, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


def _state() -> dict:
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(st: dict) -> None:
    os.makedirs(QDIR, exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as fh:
        json.dump(st, fh, indent=1)


# ------------------------------------------------------------------ windows
def any_hour() -> bool:
    """OFF SCHEDULE (2026-10-10, Barry: "Ilnora goes as soon as you get everything right. she is off schedule now").
    Live setting video_build_window = "any" -> builds start whenever the card is free (turns in flight and his
    renders still come first); anything else -> her evening slot below. No restart needed to flip it."""
    try:
        return (memory.get_setting("video_build_window") or "").strip().lower() == "any"
    except Exception:  # noqa: BLE001
        return False


def in_window(now: datetime.datetime | None = None) -> bool:
    if any_hour():
        return True
    now = now or datetime.datetime.now()
    # HER SLOT IS AFTER 6 (2026-10-07, Barry: "ilnora only generates ater work hours" / "so make thar her time slot
    # after 6"). Every day 18:00 -> 09:00 next morning; no daytime builds on any day (Sunday-all-day removed).
    return now.hour >= 18 or now.hour < 9


def minutes_left(now: datetime.datetime | None = None) -> float:
    if any_hour():
        return 24 * 60.0                                  # no window end -- any job fits
    now = now or datetime.datetime.now()
    if not in_window(now):
        return 0.0
    t = now
    while in_window(t):
        t += datetime.timedelta(minutes=15)
    return (t - now).total_seconds() / 60


# ------------------------------------------------------------------ queue
def _jobs() -> list[dict]:
    out = []
    if not os.path.isdir(QDIR):
        return out
    for f in sorted(os.listdir(QDIR)):
        if f.startswith("job_") and f.endswith(".json"):
            try:
                j = json.load(open(os.path.join(QDIR, f), encoding="utf-8"))
                j["_file"] = os.path.join(QDIR, f)
                out.append(j)
            except (OSError, ValueError):
                pass
    return out


def _write(job: dict) -> None:
    path = job.pop("_file")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(job, fh, indent=1, ensure_ascii=False)
    job["_file"] = path


def queued(kind: str | None = None) -> list[dict]:
    return [j for j in _jobs() if j.get("status") == "queued" and (kind is None or j["pkg"].get("format") == kind)]


# HOLD / RELEASE (2026-10-10, Sophie's office_ops): no build STARTS while the hold stands; a build already on the
# card is never interrupted. A file so it survives a restart; stale holds expire on their own.
_HOLD = os.path.join(QDIR, "hold_until.txt")


def held_until() -> float:
    try:
        return float(open(_HOLD, encoding="utf-8").read().strip() or 0)
    except (OSError, ValueError):
        return 0.0


def hold_builds(minutes: int, why: str = "") -> float:
    minutes = max(5, min(240, int(minutes or 30)))
    until = time.time() + minutes * 60
    os.makedirs(QDIR, exist_ok=True)
    open(_HOLD, "w", encoding="utf-8").write(f"{until:.0f}\n")
    _log(f"builds HELD for {minutes} min{(' -- ' + why) if why else ''}")
    return until


def release_builds() -> None:
    try:
        os.remove(_HOLD)
        _log("builds RELEASED")
    except OSError:
        pass


def set_job_status(title: str, new_status: str) -> dict:
    """pause (queued -> paused), resume (paused -> queued), requeue (failed/done/paused -> queued) by title prefix."""
    t = (title or "").strip().lower()
    hits = [j for j in _jobs() if t and str(j.get("pkg", {}).get("title", "")).lower().startswith(t)]
    if not hits:
        return {"error": f"no job whose title starts with {title!r}"}
    if len(hits) > 1:
        hits.sort(key=lambda j: j.get("queued") or j.get("started") or "", reverse=True)
    job = hits[0]
    allowed = {"paused": ("queued",), "queued": ("paused", "failed", "done")}
    if job.get("status") == "building":
        return {"error": f"'{job['pkg'].get('title')}' is building right now -- never interrupted; let it finish"}
    if job.get("status") not in allowed.get(new_status, ()):
        return {"error": f"'{job['pkg'].get('title')}' is {job.get('status')!r}; cannot move it to {new_status!r}"}
    old = job.get("status")
    job["status"] = new_status
    if new_status == "queued":
        job.pop("finished", None)
        job.pop("minutes", None)
    _write(job)
    _log(f"job '{job['pkg'].get('title')}' {old} -> {new_status} (office_ops)")
    return {"title": job["pkg"].get("title"), "was": old, "now": new_status}


def made_titles() -> list[str]:
    """Every video of the new (talking/animated) pipeline: queued, building, done -- or paused (written = taken)."""
    return [j["pkg"].get("title", "") for j in made_jobs()]


def find_made(title: str) -> dict | None:
    """The made video a redo names (exact title, or its start/main words). None if there is none."""
    import video_tool
    t = video_tool._norm(title or "")
    if len(t) < 4:
        return None
    jobs = made_jobs()
    for j in jobs:
        if video_tool._norm(j["pkg"].get("title", "")) == t:
            return j
    for j in jobs:
        n = video_tool._norm(j["pkg"].get("title", ""))
        if min(len(n), len(t)) >= 8 and (t in n or n in t):
            return j
    return None


def made_jobs() -> list[dict]:
    """The videos that count as made for the no-remake checks (2026-10-07, Barry: "no remakes. all new vids and all
    new plants")."""
    return [j for j in _jobs() if j.get("status") in ("queued", "building", "done", "paused")]


def queued_titles() -> list[str]:
    # paused = written and waiting: its topic is TAKEN (2026-10-07, Barry: "no remakes. all new vids and all new
    # plants" -- she rewrote a paused topic, The Green Fairy, because only queued/building titles were listed)
    return [j["pkg"].get("title", "") for j in _jobs() if j.get("status") in ("queued", "building", "paused")]


def estimate_minutes(pkg: dict) -> int:
    """Card minutes, from 2026-10-02/03 measurements: her talking ~2.2 min per spoken second, plant still ~10, other
    still ~1.5, her directed still ~2, voice ~0.25 per part, assembly ~5."""
    import video_tool
    sc = pkg["scenes"]
    talk_s = sum(len(s["narration"].split()) / video_tool.WORDS_PER_SECOND for s in sc if s.get("show") == "self")
    plants = sum(1 for s in sc if s.get("plant") and s.get("show") != "self")
    pics = sum(1 for s in sc if s.get("image_prompt") and not s.get("plant") and s.get("show") != "self")
    shots = sum(1 for s in sc if s.get("show") == "self" and s.get("shot"))
    moving = sum(1 for s in sc if s.get("motion") and s.get("show") != "self")
    return round(talk_s * 2.2 + plants * 10 + pics * 1.5 + shots * 2 + moving * 15 + len(sc) * 0.25 + 5)


def enqueue(agent_id: str, pkg: dict) -> dict:
    os.makedirs(QDIR, exist_ok=True)
    for k in ("_fact_flags", "_sources"):
        pkg.pop(k, None)
    slug = re.sub(r"[^A-Za-z0-9]+", "_", pkg.get("title") or "video").strip("_")[:40]
    job = {"agent": agent_id, "pkg": pkg, "status": "queued", "created": datetime.datetime.now().isoformat(),
           "estimate_min": estimate_minutes(pkg)}
    path = os.path.join(QDIR, f"job_{datetime.datetime.now():%Y%m%d_%H%M%S_%f}_{slug}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(job, fh, indent=1, ensure_ascii=False)
    ahead = len(queued()) - 1
    _log(f"queued '{pkg.get('title')}' ({pkg.get('format')}, ~{job['estimate_min']} min of card) -- {ahead} ahead")
    try:
        _close_redo(pkg)
    except Exception as exc:  # noqa: BLE001 -- a docket hiccup never costs a queued video
        _log(f"redo docket: {type(exc).__name__}: {exc}")
    if pkg.get("redo_of"):                               # Barry's redo: the old version is replaced (file kept)
        old = next((j for j in made_jobs() if j["pkg"].get("title") == pkg["redo_of"]), None)
        if old:
            old["status"], old["replaced_by"] = "replaced", pkg.get("title")
            _write(old)
            _log(f"redo: '{pkg['redo_of']}' replaced by '{pkg.get('title')}'")
    return {"queued": True, "videos_ahead": ahead, "card_minutes_about": job["estimate_min"]}


REVIEW_SCHEMA = {"type": "object", "required": ["ok", "problems"], "properties": {
    "ok": {"type": "boolean"},
    "problems": {"type": "array", "items": {"type": "object", "required": ["frame", "what", "fix"], "properties": {
        "frame": {"type": "integer"}, "what": {"type": "string"}, "fix": {"type": "string"}}}}}}


async def proofread(job: dict, mp4: str) -> dict | None:
    """Her proofread of a finished video (2026-10-08). One frame per part, described by the office's eyes, judged by
    her against her own plan; the review lands on Barry's DESK with the frames. Returns the review (or None)."""
    import agent_files
    import media_understanding
    pkg = job["pkg"]
    title = pkg.get("title") or "video"
    scenes = pkg.get("scenes") or []
    try:
        frames = media_understanding.extract_frames(mp4, count=max(6, min(20, len(scenes))))
    except Exception as exc:  # noqa: BLE001
        _log(f"proofread '{title}': no frames ({type(exc).__name__}: {exc})")
        return None
    if not frames:
        return None
    d = os.path.join(os.path.dirname(mp4), "proof")
    os.makedirs(d, exist_ok=True)
    plants = sorted({str(s.get("plant")) for s in scenes if s.get("plant")})
    outfit = next((" ".join(str(s.get("shot") or "").split()) for s in scenes if s.get("show") == "self" and s.get("shot")), "")
    question = ("Describe exactly what is on screen, literally: if a person is shown, their clothing (garment and colour), "
                "face and hands; if a plant is shown, its flower colour, petal count, leaf shape; any text, letters, "
                "labels or captions anywhere; anything odd (extra fingers, warped face). Report only "
                "what is visibly there.")
    seen = []
    for k, (t, data) in enumerate(frames, 1):
        p = os.path.join(d, f"frame{k:02d}_{int(t)}s.jpg")
        with open(p, "wb") as fh:
            fh.write(data)
        try:
            desc = await asyncio.to_thread(media_understanding.describe_image, data, question)
        except Exception as exc:  # noqa: BLE001
            desc = f"(the office's eyes failed: {type(exc).__name__})"
        seen.append({"frame": k, "at": f"{int(t) // 60}:{int(t) % 60:02d}", "path": p, "seen": " ".join(str(desc).split())})
    listing = "\n".join(f"frame {s['frame']} ({s['at']}): {s['seen']}" for s in seen)
    msg = (f'Your video "{title}" is built. PROOFREAD IT before Barry sees it. Here is what is on screen in '
           f"{len(seen)} frames, in order, described literally by the office's eyes:\n\n{listing}\n\n"
           f"Check your own work against your plan: ONE outfit for the whole video (your first shot: {outfit or 'none named'}); "
           f"every plant on screen looks like the real species ({', '.join(plants) or 'none'}); nothing written on "
           f"screen; you look like yourself. Answer as JSON only: "
           f'{{"ok": true/false, "problems": [{{"frame": N, "what": "...", "fix": "..."}}]}} -- an empty problems '
           f"list when it all holds.")
    data = await _ask(msg, schema=REVIEW_SCHEMA, activity=f"proofreading '{title}'")
    review = _json_reply(data) or {"ok": False, "problems": [{"frame": 0, "what": "no review came back", "fix": ""}]}
    review["frames"] = [{"frame": s["frame"], "at": s["at"], "path": s["path"]} for s in seen]
    lines = [f"PROOFREAD -- {title}", "", f"Verdict: {'OK' if review.get('ok') else 'PROBLEMS'}", ""]
    for pr in review.get("problems") or []:
        fr = next((s for s in seen if s["frame"] == pr.get("frame")), None)
        lines.append(f"- frame {pr.get('frame')}{' (' + fr['at'] + ')' if fr else ''}: {pr.get('what')} -> {pr.get('fix')}")
    lines += ["", "What the office's eyes saw, frame by frame:", ""] + [f"- frame {s['frame']} ({s['at']}): {s['seen']}" for s in seen]
    lines += ["", "Frames: " + d]
    try:
        agent_files.write_file("ilnora", f"PROOFREAD - {title}.md", "\n".join(lines),
                               what_it_is=f"her proofread of '{title}'", agent_id="ilnora")
    except Exception as exc:  # noqa: BLE001
        _log(f"proofread '{title}': desk note failed ({type(exc).__name__}: {exc})")
    _log(f"proofread '{title}': {'OK' if review.get('ok') else str(len(review.get('problems') or [])) + ' problem(s)'}")
    return review


STORYBOARD_SCHEMA = {"type": "object", "required": ["redo"], "properties": {
    "redo": {"type": "array", "items": {"type": "object", "required": ["part", "what", "picture"], "properties": {
        "part": {"type": "integer"}, "what": {"type": "string"}, "picture": {"type": "string"}}}}}}


def storyboard_for(job: dict):
    """Her storyboard check (2026-10-10, Barry: "do 1"): the build's stills, described by the office's eyes, judged
    by her against her plan BEFORE any card time goes into animating them. Returns the async check reel_builder
    calls; the parts she writes again come back as [{"part", "what", "picture"}] and are recorded on the job."""
    async def check(parts: list[dict]) -> list[dict]:
        import comfy_image
        import media_understanding
        title = job["pkg"].get("title") or "video"
        await comfy_image.unload()                      # the picture models off the card before the eyes load
        question = ("Describe exactly what is on screen, literally: if a person is shown, their clothing (garment and "
                    "colour), what they hold, face and hands; if a plant is shown, its flower colour and shape, petal "
                    "count, leaf shape; any text, letters or labels anywhere; anything odd (extra fingers, warped face, "
                    "a prop nobody asked for). Report only what is visibly there.")
        rows = []
        for p in parts:
            try:
                with open(p["path"], "rb") as fh:
                    desc = await asyncio.to_thread(media_understanding.describe_image, fh.read(), question)
            except Exception as exc:  # noqa: BLE001
                desc = f"(the office's eyes failed: {type(exc).__name__})"
            who = {"self": "YOU on camera", "photo": "REAL PHOTO of the species -- it stays",
                   "plant": f"plant picture, {p['plant']}", "drawn": "picture"}.get(p["kind"], "picture")
            rows.append(f"part {p['part']} ({who})\n  you say: {p.get('says') or '(no line)'}\n"
                        f"  you planned: {p['planned'] or '(nothing written)'}\n"
                        f"  on screen: {' '.join(str(desc).split())}")
        msg = (f'Your video "{title}" has its pictures drawn -- nothing is animated yet. LOOK AT YOUR STORYBOARD now, '
               f"while a redraw costs a minute instead of the night. Each part: what you planned, and what the "
               f"office's eyes see in the picture, described literally:\n\n" + "\n\n".join(rows) + "\n\n"
               f"Any part whose picture is wrong -- not the real species, you in a different outfit from your first "
               f"shot, something in it you did not ask for, letters on screen, warped face or hands, or a "
               f"picture that does not show what you are SAYING in that part (Barry: \"the scenes needs to match the "
               f"information being told\") -- write that part's picture again: the full new description, "
               f"in your words, one the picture engine can draw right. Real photos stay. At most 6 parts. "
               f"Answer as JSON only: "
               f'{{"redo": [{{"part": N, "what": "what is wrong", "picture": "the full new picture"}}]}} -- an empty '
               f"list when the storyboard holds.")
        data = await _ask(msg, schema=STORYBOARD_SCHEMA, activity=f"checking the storyboard of '{title}'")
        redo = (_json_reply(data) or {}).get("redo") or []
        redo = [r for r in redo if isinstance(r, dict)]
        job["storyboard"] = {"redo": redo, "seen": rows}
        _log(f"storyboard '{title}': " + (f"{len(redo)} part(s) to redraw" if redo else "holds"))
        return redo
    return check


async def _build_one(job: dict) -> None:
    import comfy_image
    import video_tool
    job["status"], job["started"] = "building", datetime.datetime.now().isoformat()
    _write(job)
    token = comfy_image.REEL_ACTIVE.set(True)
    open(comfy_image._REEL_MARK, "w").write(job["pkg"].get("title", ""))
    t0 = time.time()
    try:
        ok = await video_tool._build(job["agent"], job["pkg"], storyboard=storyboard_for(job))
    except Exception as exc:  # noqa: BLE001
        ok = False
        _log(f"build crashed: {type(exc).__name__}: {exc}")
    finally:
        comfy_image.REEL_ACTIVE.reset(token)
    try:
        await _after_build(job, ok, t0)
    finally:
        # THE FLAG STAYS UP THROUGH THE PROOFREAD (2026-10-15): it used to drop before it, so the office's own turns
        # came back early -- Sophie's learning review loaded Bonsai at 09:43 while the proofread's vision model was on
        # the card, and the AMD driver timed out at 10:03 (TDR, amdkmdag). "if she isnt finish, the office has to wait".
        try:
            os.remove(comfy_image._REEL_MARK)
        except OSError:
            pass


# ONE FOLDER PER VIDEO (Barry 2026-10-18: "each video should come with its own folder with hashtags and descriptions.
# I'm about to make a facebook page for her and tik tok soon."). Everything he needs to post sits next to the MP4:
# her own description file (the one she writes to the DESK), the thumbnail, and one ready-to-paste text per platform.
_REEL_ID = re.compile(r"(\d{8}_\d{6})\.mp4$")
_TITLE_NORM = re.compile(r"[^a-z0-9]+")


def _norm_title(s: str) -> str:
    return _TITLE_NORM.sub(" ", (s or "").lower()).strip()


def _reel_meta(mp4: str) -> dict:
    """The build's own record (data/reels/<id>/reel.json -> result): caption with credits, hashtags, thumbnail."""
    m = _REEL_ID.search(os.path.basename(mp4))
    if not m:
        return {}
    import reel_builder
    p = os.path.join(reel_builder.REELS_DIR, m.group(1), "reel.json")
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh).get("result") or {}
    except (OSError, ValueError):
        return {}


def _her_description(agent_id: str, title: str) -> str | None:
    """Her '<plant>-description.md' on the DESK whose heading is this video's title (newest first)."""
    import agent_files
    d = agent_files._agent_dir(agent_id)
    want = _norm_title(title)
    try:
        names = sorted((f for f in os.listdir(d) if f.lower().endswith("-description.md")),
                       key=lambda f: os.path.getmtime(os.path.join(d, f)), reverse=True)
    except OSError:
        return None
    for f in names:
        p = os.path.join(d, f)
        try:
            with open(p, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        head = next((ln for ln in text.splitlines() if ln.strip()), "")
        if _norm_title(head.lstrip("# ")) == want:
            return p
    return None


def _md_section(text: str, name: str) -> str:
    m = re.search(rf"^##\s*{re.escape(name)}\s*\n(.*?)(?=^##\s|\Z)", text, re.S | re.M | re.I)
    return m.group(1).strip() if m else ""


def video_folder(job: dict, mp4: str, stem: str) -> str:
    """Build FOLDER/<stem>/ with the MP4 and everything to post it. Returns the MP4's path inside it."""
    pkg = job.get("pkg") or {}
    meta = _reel_meta(mp4)
    title = pkg.get("title") or meta.get("title") or "video"
    folder = os.path.join(FOLDER, stem)
    os.makedirs(folder, exist_ok=True)
    out_mp4 = os.path.join(folder, stem + ".mp4")
    shutil.copy2(mp4, out_mp4)
    if meta.get("thumbnail") and os.path.isfile(meta["thumbnail"]):
        shutil.copy2(meta["thumbnail"], os.path.join(folder, "thumbnail.jpg"))

    # her words first: the description file she wrote; the package caption/hashtags when she wrote none
    desc_path = _her_description(job.get("agent") or "ilnora", title)
    desc_text = ""
    if desc_path:
        shutil.copy2(desc_path, os.path.join(folder, "description.md"))
        with open(desc_path, encoding="utf-8") as fh:
            desc_text = fh.read()
    description = _md_section(desc_text, "Description") or pkg.get("caption") or meta.get("caption") or ""
    caption = _md_section(desc_text, "Caption") or pkg.get("caption") or ""
    warnings = _md_section(desc_text, "Warnings")
    sci = _md_section(desc_text, "Scientific name")
    sources = _md_section(desc_text, "Sources")
    tags = (_md_section(desc_text, "Hashtags") or " ".join(pkg.get("hashtags") or meta.get("hashtags") or "")).split()
    tags = [t if t.startswith("#") else "#" + t for t in dict.fromkeys(t.strip() for t in tags if t.strip())]
    credits = (meta.get("music_credit") or "").strip()
    is_short = (pkg.get("format") or meta.get("format") or "short") == "short"
    seconds = meta.get("seconds")

    def w(name: str, text: str) -> None:
        with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
            fh.write(text.rstrip() + "\n")

    w("title.txt", title)
    w("caption.txt", caption)
    w("hashtags.txt", " ".join(tags))
    if credits:
        w("credits.txt", credits)
    body = (description + (f"\n\n{sci}" if sci else "") + (f"\n\n{warnings}" if warnings else "")
            + (f"\n\nSources:\n{sources}" if sources else ""))
    w("post-youtube.txt", f"{title}{' #shorts' if is_short else ''}\n\n{body}\n\n"
                          + (f"{credits}\n\n" if credits else "") + " ".join(tags + (["#shorts"] if is_short else [])))
    w("post-tiktok.txt", f"{caption}\n\n" + " ".join(tags + ["#fyp"]) + (f"\n\n{credits}" if credits else ""))
    w("post-facebook.txt", f"{title}\n\n{body}\n\n" + " ".join(tags) + (f"\n\n{credits}" if credits else ""))
    if job.get("review") and not job["review"].get("ok"):
        probs = job["review"].get("problems") or []
        w("PROOFREAD PROBLEMS.txt", f"Her own proofread found {len(probs)} problem(s):\n\n" + "\n\n".join(
            f"part {p.get('frame', '?')}: {p.get('what', '')}\n  fix: {p.get('fix', '')}" for p in probs if isinstance(p, dict)))
    _log(f"folder: {folder} ({'%.0f s' % seconds if seconds else 'length unknown'}, "
         f"{'her description' if desc_path else 'package caption only'}, {len(tags)} hashtags)")
    return out_mp4


async def _after_build(job: dict, ok, t0: float) -> None:
    job["status"] = "done" if ok else "failed"
    job["finished"], job["minutes"] = datetime.datetime.now().isoformat(), round((time.time() - t0) / 60)
    if isinstance(ok, str) and os.path.isfile(ok):
        try:
            job["review"] = await proofread(job, ok)       # 2026-10-08: she proofreads before Barry sees it
        except Exception as exc:  # noqa: BLE001
            _log(f"proofread crashed: {type(exc).__name__}: {exc}")
        # HIS FOLDER (Barry 2026-10-03: "just leave them all in a folder on my desktop, Ilnora's Videos")
        # ONE FOLDER PER VIDEO (Barry 2026-10-18: "each video should come with its own folder with hashtags and
        # descriptions. I'm about to make a facebook page for her and tik tok soon."): the MP4 plus thumbnail,
        # description, caption, hashtags, credits and ready-to-paste posts for YouTube / TikTok / Facebook.
        os.makedirs(FOLDER, exist_ok=True)
        title = re.sub(r'[<>:"/\\|?*]+', "", job["pkg"].get("title") or "video").strip()[:80]
        # her proofread still found problems: the name says so (Barry 2026-10-10 -- Wolf's Blood failed her own check
        # and arrived looking like any other video); the PROOFREAD note on the DESK says what
        flag = " (PROOFREAD PROBLEMS)" if job.get("review") and not job["review"].get("ok") else ""
        stem = f"{datetime.date.today():%Y-%m-%d} {job['pkg'].get('format', 'short').title()} - {title}{flag}"
        try:
            job["folder_copy"] = video_folder(job, ok, stem)
        except Exception as exc:  # noqa: BLE001
            _log(f"could not make the video folder: {type(exc).__name__}: {exc}")
            try:                                            # the old flat copy, so he still gets the video
                shutil.copy2(ok, os.path.join(FOLDER, stem + ".mp4"))
                job["folder_copy"] = os.path.join(FOLDER, stem + ".mp4")
            except OSError as exc2:
                _log(f"could not copy to {FOLDER}: {exc2}")
    _write(job)
    _log(f"{job['status']} '{job['pkg'].get('title')}' in {job['minutes']} min (estimated {job['estimate_min']})"
         + (f" -> {job['folder_copy']}" if job.get("folder_copy") else ""))


async def drain_tick() -> None:
    if not in_window():
        return
    import comfy_image
    if comfy_image.reel_building():                   # another of her builds (a redo / a test) holds the card
        return
    jobs = queued()
    if not jobs:
        return
    # NEVER TAKE THE CARD FROM A TURN IN FLIGHT (2026-10-10, Barry: "transmission just failed. Did you do
    # something?"): a build started 30 s after her turn hit the time ceiling, the pre-build eviction unloaded
    # Bonsai under her forced answer, and the reply died (ReadError). The build waits for the next tick.
    import activity
    busy_turn = activity.turn_in_flight()
    if busy_turn:
        _log(f"{len(jobs)} queued -- holding the build: {busy_turn} is mid-turn")
        return
    if held_until() > time.time():                       # Sophie's office_ops hold_builds (2026-10-10)
        return
    left = minutes_left()
    # oldest first, but never START one that can't finish inside the window (the next window picks it up)
    for job in jobs:
        # "rush": true on a job (Barry 2026-10-04: "i want to get some uploads done first") = start it even if it runs
        # past the window's end -- the office is slower until it finishes
        if job.get("rush") or job.get("estimate_min", 0) <= left + 30:
            await _build_one(job)
            return
    _log(f"{len(jobs)} queued, none fits the {left:.0f} min left in this window -- waiting for the next")


# ------------------------------------------------------------------ her writing turns
def _recent_made(n: int = 30) -> list[str]:
    import video_tool
    # titles WITH their plants (2026-10-07, Barry: "she needs to know what was done already, so she dont remake
    # them, unless the audience wants more")
    out, seen = [], set()
    for j in made_jobs():
        t = j["pkg"].get("title", "")
        plants = sorted({str(s.get("plant")) for s in j["pkg"].get("scenes") or [] if s.get("plant")})
        out.append(t + (f" -- plants: {', '.join(plants)}" if plants else ""))
        seen.add(t)
    older = [t for t in video_tool._recent_titles(AGENT, days=60) if t not in seen]
    return (older + out)[-n:]


async def _ask(message: str, schema: dict | None = None, activity: str = "making videos for tonight") -> dict:
    body = {"agent_id": AGENT, "message": message, "task": True, "personal": False, "activity": activity}
    if schema:
        body["json_schema"] = schema                     # grammar lock (bonsai_llm.json_schema_override)
    async with httpx.AsyncClient(timeout=2400) as cx:
        r = await cx.post("http://127.0.0.1:8420/api/chat", json=body)
    r.raise_for_status()
    return r.json() or {}


def _json_reply(data: dict) -> dict | None:
    """A locked pass answers with bare JSON (no fence); fall back to the fenced finder."""
    txt = (data.get("reply") or "").strip()
    try:
        v = json.loads(txt)
        return v if isinstance(v, dict) else None
    except json.JSONDecodeError:
        m = re.search(r"(\{.*\})", txt, re.S)
        if m:
            try:
                v = json.loads(m.group(1))
                return v if isinstance(v, dict) else None
            except json.JSONDecodeError:
                return None
    return None


# ------------------------------------------------------------------ SECTIONS (2026-10-07, Barry: "build both, the
# grammar lock and the sections"). A 10-minute script asked for in one breath never came back tonight -- three
# turns of outlines and "I've written it to ~1,747 words". AgentWrite / LongWriter method: plan the parts, write
# a few at a time, assemble; each pass is grammar-locked so prose is not an option. Her words stay hers.
_PART_PLAN = {"type": "object", "required": ["n", "covers", "show"], "properties": {
    "n": {"type": "integer"},
    "covers": {"type": "string"},
    "show": {"type": "string"},
    "shot": {"type": "string"},
    "plant": {"type": "string"},
    "motion": {"type": "boolean"},
    "move": {"type": "string"}}}
PLAN_SCHEMA = {"type": "object", "required": ["title", "mood", "caption", "hashtags", "parts"], "properties": {
    "title": {"type": "string"},
    "mood": {"type": "string", "enum": ["spooky", "calm", "upbeat", "mystic"]},
    "caption": {"type": "string"},
    "hashtags": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 6},
    "parts": {"type": "array", "items": _PART_PLAN, "minItems": 10, "maxItems": 20}}}
SAY_SCHEMA = {"type": "object", "required": ["parts"], "properties": {
    "parts": {"type": "array", "items": {"type": "object", "required": ["n", "say"], "properties": {
        "n": {"type": "integer"}, "say": {"type": "string"}}}}}}
_PART_FULL = {"type": "object", "required": ["say", "show"], "properties": {
    "say": {"type": "string"}, "show": {"type": "string"}, "shot": {"type": "string"}, "plant": {"type": "string"},
    "motion": {"type": "boolean"}, "move": {"type": "string"}}}
VIDEO_SCHEMA = {"type": "object", "required": ["title", "format", "mood", "parts", "caption", "hashtags"], "properties": {
    "title": {"type": "string"},
    "format": {"type": "string", "enum": ["short", "long"]},
    "mood": {"type": "string", "enum": ["spooky", "calm", "upbeat", "mystic"]},
    "parts": {"type": "array", "items": _PART_FULL, "minItems": 1},
    "caption": {"type": "string"},
    "hashtags": {"type": "array", "items": {"type": "string"}}}}
LONG_TARGET_WORDS = 2300         # sections flow target, above video_tool.LONG_GOAL_WORDS (8 min); she writes ~80% of a target
SECTION_SIZE = 4


def _brief(slot_label: str, form: str) -> str:
    plan = _plan_text()
    made = _recent_made()
    return ((f"FROM BARRY:\n{_note_text()}\n\n" if _note_text() else "")
            + (f"YOUR PLAN FOR THE WEEK (you wrote it):\n{plan}\n\n" if plan else "")
            + ("VIDEOS ALREADY MADE OR WAITING TO BUILD (newest last):\n- " + "\n- ".join(made) + "\n\n" if made else ""))


def _assemble(plan: dict, says: dict) -> dict:
    parts = []
    for p in sorted(plan.get("parts") or [], key=lambda x: int(x.get("n") or 0)):
        n = int(p.get("n") or 0)
        q = {"say": says.get(n, ""), "show": p.get("show") or "me"}
        for k in ("shot", "plant", "move"):
            if (p.get(k) or "").strip():
                q[k] = p[k]
        if p.get("motion") is True:
            q["motion"] = True
        parts.append(q)
    return {"title": plan.get("title") or "untitled", "format": "long", "mood": plan.get("mood") or "mystic",
            "parts": parts, "caption": plan.get("caption") or "", "hashtags": plan.get("hashtags") or []}


async def expand_long(video: dict, slot_label: str, need: int) -> dict:
    """Add `need` words by expanding the SHORTEST parts with a locked SAY pass (2026-10-07: the whole-video fix pass
    came back unchanged twice; a pass aimed at named parts lands)."""
    parts = video.get("parts") or []
    order = sorted(range(len(parts)), key=lambda i: len(str(parts[i].get("say", "")).split()))
    pick = sorted(order[:max(3, min(5, len(parts)))])
    per = -(-(need + 60) // len(pick))
    listing = "\n".join(f"{i + 1}. ({len(str(parts[i].get('say', '')).split())} words) {parts[i].get('say', '')}"
                        for i in pick)
    msg = (f'"{video.get("title")}" is {need} words short of a Long. Rewrite parts {", ".join(str(i + 1) for i in pick)} '
           f"LONGER -- each about {per} more words than it has now: more of the story, the detail, the practice, "
           f"the warning, in your spoken voice. Keep what each part covers. Facts only from your notes. Answer as JSON "
           f'only: {{"parts": [{{"n": N, "say": "..."}}]}}.\n\nTHE PARTS TO EXPAND:\n{listing}')
    data = await _ask(msg, schema=SAY_SCHEMA, activity="expanding tonight's Long")
    got = _json_reply(data) or {}
    for item in got.get("parts") or []:
        try:
            n = int(item.get("n"))
        except (TypeError, ValueError):
            continue
        say = " ".join(str(item.get("say") or "").split())
        if 1 <= n <= len(parts) and len(say.split()) > len(str(parts[n - 1].get("say", "")).split()):
            parts[n - 1]["say"] = say
    video["parts"] = parts
    return video


async def fact_pass(video: dict, sources: list[str], slot_label: str) -> dict:
    """FACT NET (2026-10-08): every sentence against what she read; flagged parts go back to her, twice at most.
    Returns the (possibly revised) video; leftover flags are stored on it as "_fact_flags" for Barry."""
    import fact_net
    if not sources:
        _log(f"{slot_label}: fact net skipped -- no sources captured")
        return video
    for _round in range(3):
        res = fact_net.check_video(video, sources)
        _log(f"{slot_label}: fact net checked {res['checked']} sentences, {len(res['flags'])} flagged"
             + (f" ({res['note']})" if res.get("note") else ""))
        if res["ok"] or _round == 2:
            video["_fact_flags"] = res["flags"]
            return video
        parts_hit = sorted({f["part"] for f in res["flags"]})
        listing = "\n".join(f"{n}. {video['parts'][n - 1].get('say', '')}" for n in parts_hit)
        # THE RECORDS, next to each flagged part: the two captured sources that share the most words with it
        stop = set("the a an and or of to in on for with by as is are was were be it its this that from at not".split())

        def words(s):
            return {w for w in re.findall(r"[a-z][a-z\-]{2,}", s.lower()) if w not in stop}
        src_words = [words(s) for s in sources]
        records = []
        for n in parts_hit:
            pw = words(str(video["parts"][n - 1].get("say", "")))
            best = sorted(range(len(sources)), key=lambda i: -len(pw & src_words[i]))[:2]
            picked = "\n".join("  " + " ".join(sources[i].split())[:1500] for i in best if pw & src_words[i])
            records.append(f"part {n}:\n{picked or '  (nothing you read matches this part)'}")
        msg = (fact_net.send_back_text(res["flags"])
               + "\n\nWHAT YOU ACTUALLY READ, for each part (write from THIS -- in your voice, but only what it "
                 "says; a legend or a claim you cannot find here is said as a legend, or cut):\n" + "\n".join(records)
               + f'\n\nAnswer as JSON only: {{"parts": [{{"n": N, "say": "..."}}]}} for parts {", ".join(map(str, parts_hit))}.'
               f"\n\nTHE PARTS AS THEY ARE:\n{listing}")
        data = await _ask(msg, schema=SAY_SCHEMA, activity="fixing facts in tonight's Long")
        got = _json_reply(data) or {}
        for item in got.get("parts") or []:
            try:
                n = int(item.get("n"))
            except (TypeError, ValueError):
                continue
            say = " ".join(str(item.get("say") or "").split())
            if n in parts_hit and say:
                video["parts"][n - 1]["say"] = say
    return video


async def finish_long(video: dict, slot_label: str, sources: list[str] | None = None) -> bool:
    """The check, with a length send-back answered by expansion and any other send-back by one locked fix pass."""
    import video_tool
    before = len(queued())
    video = await fact_pass(video, sources or [], slot_label)
    for _round in range(4):
        res = await _submit(video, "long")
        if res.get("queued") or res.get("started") or len(queued()) > before:
            _log(f"{slot_label}: Long queued in sections ({sum(len(str(p.get('say', '')).split()) for p in video['parts'])} words)")
            return True
        fix = res.get("fix_this")
        if not fix or _round == 3:
            break
        words = sum(len(str(p.get("say", "")).split()) for p in video["parts"])
        if "words or more spoken" in str(fix) and words < video_tool.LONG_MIN_WORDS:
            _log(f"{slot_label}: {words} words -- expanding the shortest parts")
            video = await expand_long(video, slot_label, video_tool.LONG_MIN_WORDS - words)
            video_tool.save_draft(AGENT, video, str(fix))
            continue
        _log(f"{slot_label}: sent back ({str(fix)[:120]}) -- one locked fix pass")
        data = await _ask("The office checked your video and sent it back for one thing: " + str(fix)
                          + "\n\nHere is the whole video. Change only that and answer with the whole video as JSON "
                            "(title, format, mood, parts, caption, hashtags).\n```json\n"
                          + json.dumps(video, ensure_ascii=False) + "\n```", schema=VIDEO_SCHEMA,
                          activity="fixing tonight's Long")
        fixed = _json_reply(data)
        if fixed and fixed.get("parts"):
            fixed["_sources"] = video.get("_sources") or []        # the captured sources ride along
            video = fixed
            video["format"] = "long"
    _log(f"{slot_label}: Long did not queue after the fix passes")
    return False


# ------------------------------------------------------------------ THE DRAFT WORKSPACE (2026-10-10)
# Barry: "think deeper and come up with something better or more stable" -> "go, build the workspace". The script
# lives in a FILE (video_tool.draft); she builds it a few parts per SHORT turn, the office reads the file between
# turns and asks for the next stage. No turn ever carries the whole script, so the 15-minute ceiling, the 4,096
# forced-answer cap and "the same draft resent three times" cannot happen. Each stage prompt starts with
# "[video draft: <stage>]" -- main.py gives that stage a normal-sized budget. Falls back to the 10-07 sections
# flow (write_long_sections) if the draft never starts.
DRAFT_PARTS_PER_TURN = 4
DRAFT_MAX_PART_TURNS = 10


def _draft_outline(d: dict) -> str:
    parts = d.get("parts") or []
    if not parts:
        return "(no parts yet)"
    return "\n".join(f"{i}. ({len(str(p.get('say') or '').split())} words) "
                     f"{'[you on camera] ' if str(p.get('show') or '').strip().lower() in ('me', 'self', 'myself', 'ilnora') else ''}"
                     f"{' '.join(str(p.get('say') or '').split()[:14])}..." for i, p in enumerate(parts, 1))


def _draft_script(d: dict) -> str:
    """Every saved part IN FULL -- what she says and what is on screen. 2026-10-14: the 14-word outline left her
    writing chapters blind ("I need to see the exact spoken lines so I don't repeat"); the pumpkin Long rewrote
    chapter 3 three times, 17 repeats were cut at the check and it shipped at 829 words (4:27)."""
    parts = d.get("parts") or []
    if not parts:
        return "(no parts yet)"
    return "\n".join(f"{i}. SAY: {' '.join(str(p.get('say') or '').split())}\n   SHOW: "
                     f"{' '.join(str(p.get('show') or '').split())}" for i, p in enumerate(parts, 1))


async def write_long_draft(slot_label: str, ask: str = "") -> bool:
    """The week's Long through the draft workspace. True when it queued."""
    import video_tool
    before = len(queued())
    brief = _brief(slot_label, "long")
    floor = video_tool.LONG_GOAL_WORDS
    # his note rides every chapter turn too (2026-10-15: it reached only the research turn, so "I need to see the
    # mystical stuff in this video", added mid-run, never reached the chapters she was writing)
    barry = ((f"THIS VIDEO, FROM BARRY: {ask}\n\n" if ask else "")
             + (f"FROM BARRY:\n{_note_text()}\n\n" if _note_text() else ""))
    # stage 1: research -> she starts the draft and saves her notes (tools on)
    old = video_tool.load_draft(AGENT)
    if old and (old.get("parts") or old.get("notes")) and time.time() - float(old.get("updated") or 0) < 36 * 3600:
        _log(f"{slot_label}: resuming the draft '{old.get('title')}' ({len(old.get('parts') or [])} parts)")
    else:
        await _ask("[video draft: research] " + barry
                   + f"Scheduled job from the office ({slot_label}): tonight you make a Long video (widescreen, "
                     f"{LONG_MINUTES} minutes or more spoken, {floor} words or more). Use your video_draft tool: "
                     "FIRST call it with action \"start\" (title, format \"long\", mood). THEN research -- "
                     + ("it is the video Barry named above -- that plant, that story; " if ask else
                        "pick the plant(s) with the steps in your make-video-masterfully skill; ")
                     + "read the sections in your library and anything on PubMed you will lean on, and search_web how "
                       "other channels already covered it -- and save what you found with action \"notes\": the "
                       "plant(s), the facts you will use (each with where it came from), one line on what the field "
                       "already did, your look for your own parts (ONE outfit for every chapter), and the CHAPTER "
                       "PLAN -- five or six chapters of about 2 minutes (350-400 words each), one line per chapter: "
                       "what it is for, its turn, its hook out. No script yet; the office asks for one chapter at a "
                       "time next.\n\n" + brief,
                   activity="researching tonight's Long")
        if not video_tool.load_draft(AGENT):
            await _ask("[video draft: research] Nothing was saved: the draft was not started. Call video_draft with "
                       "action \"start\" (title, format \"long\", mood) now, then action \"notes\" with your research "
                       "notes. Nothing else.", activity="starting tonight's Long")
    d = video_tool.load_draft(AGENT)
    if not d:
        _log(f"{slot_label}: the draft never started -- falling back to the sections flow")
        return await write_long_sections(slot_label, ask)
    # stage 2: the parts, a few per short turn, until the floor
    stalls = 0
    def _heard(dd):          # (words the viewer hears once, repeats) -- repeats never count toward the length
        says = [str(p.get("say") or "") for p in dd.get("parts") or []]
        reps = video_tool.repeated_parts(says)
        cut = {a for a, _b in reps}
        return sum(len(s.split()) for k, s in enumerate(says, 1) if k not in cut), reps

    closed = False                  # her closing chapter was asked for: past 7 minutes, the story is done
    for _turn in range(DRAFT_MAX_PART_TURNS):
        st = video_tool.draft_status(d)
        heard, reps = _heard(d)
        if not reps and (heard >= floor or (closed and heard >= video_tool.LONG_MIN_WORDS)):
            break
        closed = closed or heard >= floor - 450
        n0 = st["parts_so_far"]
        notes = " ".join(d.get("notes") or [])
        first = ("FIRST: these parts repeat an earlier part -- the viewer would hear them twice: "
                 + "; ".join(f"part {a} repeats part {b}" for a, b in reps)
                 + ". Remove them (video_draft action \"remove_part\", highest number first) before you add "
                   "anything.\n\n") if reps else ""
        await _ask(f"[video draft: parts] {first}Your Long \"{d.get('title')}\": {n0} parts saved, {heard} words the "
                   f"viewer hears (about {heard / video_tool.LONG_WORDS_PER_SECOND / 60:.1f} minutes; Barry wants at "
                   f"least {LONG_MINUTES} -- about {floor} words). Your whole script so far is below: continue the "
                   f"story from where it ends -- never write a chapter you already have. "
                   # the ending (2026-10-14, Barry: "she needs to know how a story should end"): the loop never said
                   # which chapter was the last, so a Long could stop at the word goal mid-story
                   + (f"This is your CLOSING chapter: it completes the story -- the payoff and your last image and "
                      f"line (your make-epic-videos skill). " if heard >= floor - 450 else "")
                   + f"Write the NEXT CHAPTER "
                   f"of your chapter plan now (Barry: \"break it up into like five or six 2 minutes and put them "
                   f"together\") -- about 350-400 words, its own hook in and a hook out into the next chapter. Shot "
                   f"list first (your my-filmmaking skill), then full spoken lines to fit the pictures, the way you "
                   f"talk on camera, facts only from your notes -- and save the chapter's parts with video_draft "
                   f"action \"add_parts\" (say, show; shot when you are on "
                   f"camera -- name your outfit once, in your first shot; plant's scientific name when a plant is on "
                   f"screen; motion + move where something happens). You are on camera for the intro, a quick safety "
                   f"note and a 2-second outro; the rest is your voice over the pictures. Call the tool; writing the "
                   f"parts in your reply saves nothing.\n\nYOUR NOTES:\n{notes[:6000]}\n\nYOUR SCRIPT SO FAR:\n"
                   + _draft_script(d) + "\n\n" + barry,
                   activity=f"writing chapter {_turn + 1} of tonight's Long")
        d2 = video_tool.load_draft(AGENT) or d
        if _heard(d2)[0] <= heard and len(_heard(d2)[1]) >= len(reps):
            stalls += 1
            _log(f"{slot_label}: parts turn saved nothing ({stalls}/2)")
            if stalls >= 2:
                break
        else:
            stalls = 0
        d = d2
        _log(f"{slot_label}: draft at {video_tool.draft_status(d)['total_words']} words, {len(d.get('parts') or [])} parts")
    # stage 3: check -> replace_part -> send (caption + hashtags)
    for _round in range(4):
        d = video_tool.load_draft(AGENT)
        if not d:                                       # archived = sent
            break
        res = await video_tool.draft(AGENT, {"action": "check"})
        fix = res.get("fix_this")
        await _ask("[video draft: check] " + (f"The office checked your draft \"{d.get('title')}\" and sent it back "
                                              f"for one thing: {fix}\n\nFix that with video_draft action "
                                              f"\"replace_part\" (n, part) or \"add_parts\", then call action "
                                              f"\"send\" with a caption and 3-6 hashtags."
                                              if fix else
                                              f"Your draft \"{d.get('title')}\" passes the office's checks. Call "
                                              f"video_draft action \"send\" now with a caption and 3-6 hashtags; "
                                              f"it queues to build tonight.")
                   + "\n\nYOUR SCRIPT:\n" + _draft_script(d), activity="finishing tonight's Long")
        if len(queued()) > before:
            _log(f"{slot_label}: Long queued from the draft workspace")
            return True
    if len(queued()) > before:
        return True
    _log(f"{slot_label}: the draft did not send after the check passes -- it stays saved for the next slot")
    return False


async def write_long(slot_label: str, ask: str = "") -> bool:
    """The week's Long: the draft workspace first (2026-10-10); the sections flow is the fallback."""
    return await write_long_draft(slot_label, ask)


async def write_long_sections(slot_label: str, ask: str = "") -> bool:
    """The week's Long, in sections (2026-10-07). True when it queued."""
    import video_tool
    before = len(queued())
    brief = _brief(slot_label, "long")
    # 1. research -- thinking and tools on, no grammar: her notes
    notes = await _ask((f"THIS VIDEO, FROM BARRY: {ask}\n\n" if ask else "")
                       + f"Scheduled job from the office ({slot_label}): tonight you make a Long video "
                       f"(widescreen, {LONG_MINUTES} minutes or more spoken, {video_tool.LONG_GOAL_WORDS} words or more). FIRST, research it: "
                       + ("it is the video Barry named above -- that plant, that story; " if ask else
                          "pick the plant(s) with the steps in your make-video-masterfully skill, ")
                       + "read the sections in "
                       "your library and anything on PubMed you will lean on, and reply with your NOTES -- the plant(s), "
                       "the facts you will use (each with where it came from), the story's shape, and your look for "
                       "your own parts. No script yet; the office asks for it next, part by part.\n\n"
                       + (f"FROM BARRY, FOR THIS VIDEO:\n{ask}\n\n" if ask else "") + brief,
                       activity="researching tonight's Long")
    sources = [s for s in (notes.get("sources") or []) if s]
    _log(f"{slot_label}: research notes {len((notes.get('reply') or '').split())} words, "
         f"{len(sources)} sources ({sum(len(s.split()) for s in sources)} words)")
    # 2. the plan, locked
    data = await _ask((f"THIS VIDEO, FROM BARRY: {ask}\n\n" if ask else "")
                      + "Now plan the Long from your notes, as JSON only: title, mood (spooky|calm|upbeat|mystic), "
                      "caption, hashtags (3-6), and parts (12 to 18). For each part: n, covers (what this part says, "
                      "in a sentence), show (\"me\" when you are on camera, else a full-sentence description of the "
                      "picture), shot (when show is me: outfit and colour, place, what you are doing, how close the "
                      "camera is -- name the outfit once, in your first shot), plant (the scientific name whenever a "
                      "plant is on screen), motion (true for a moving picture) and move (what moves, like a camera "
                      "operator). You are on camera for the intro, your quick safety note and a 2-second outro; the "
                      "rest is your voice over the plants and pictures. Do not write the spoken lines yet.",
                      schema=PLAN_SCHEMA, activity="planning tonight's Long")
    plan = _json_reply(data)
    if not plan or not plan.get("parts"):
        _log(f"{slot_label}: no plan came back (locked pass) -- {len(data.get('reply') or '')} chars")
        return False
    plan["parts"] = [p for p in plan["parts"] if isinstance(p, dict)]
    for i, p in enumerate(plan["parts"], 1):
        p["n"] = i
    n_parts = len(plan["parts"])
    per_part = -(-LONG_TARGET_WORDS // n_parts)
    _log(f"{slot_label}: plan '{plan.get('title')}' -- {n_parts} parts, ~{per_part} words each")
    # 3. the lines, a few parts at a time, locked
    says: dict[int, str] = {}
    outline = "\n".join(f"{p['n']}. {'[you on camera] ' if str(p.get('show', '')).strip().lower() in ('me', 'self') else ''}"
                        f"{p.get('covers', '')}" for p in plan["parts"])
    for start in range(0, n_parts, SECTION_SIZE):
        chunk = plan["parts"][start:start + SECTION_SIZE]
        ns = [p["n"] for p in chunk]
        written = "\n".join(f"{n}. {says[n]}" for n in sorted(says)) or "(nothing yet)"
        need = LONG_TARGET_WORDS - sum(len(s.split()) for s in says.values())
        left_parts = n_parts - len(says)
        target = max(per_part, -(-need // max(1, left_parts)))
        msg = (f'Write what you SAY in parts {ns[0]} to {ns[-1]} of "{plan.get("title")}", as JSON only: '
               f'{{"parts": [{{"n": N, "say": "..."}}]}}. About {target} words per part -- full, spoken, the way you '
               f"talk on camera; the whole video must reach {video_tool.LONG_GOAL_WORDS} words. Facts only from your notes.\n\n"
               f"THE PARTS (the whole video):\n{outline}\n\nTHESE PARTS NOW:\n"
               + "\n".join(f"{p['n']}. {p.get('covers', '')} -- on screen: {p.get('show', '')}" for p in chunk)
               + f"\n\nALREADY WRITTEN:\n{written}")
        data = await _ask(msg, schema=SAY_SCHEMA, activity=f"writing parts {ns[0]}-{ns[-1]} of tonight's Long")
        got = _json_reply(data) or {}
        for item in got.get("parts") or []:
            try:
                if int(item.get("n")) in ns and str(item.get("say") or "").strip():
                    says[int(item["n"])] = " ".join(str(item["say"]).split())
            except (TypeError, ValueError):
                pass
        _log(f"{slot_label}: parts {ns[0]}-{ns[-1]} -> {sum(len(s.split()) for s in says.values())} words so far")
    video = _assemble(plan, says)
    video["_sources"] = sources
    # 4. the fact net, then the same check as always; short = expand the shortest parts; else one locked fix pass
    return await finish_long(video, slot_label, sources)


def _video_json(reply: str) -> dict | None:
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", reply or "", re.S) or re.search(r"(\{.*\})", reply or "", re.S)
    if not m:
        return None
    try:
        v = json.loads(m.group(1))
        return v if isinstance(v, dict) and v.get("parts") else None
    except json.JSONDecodeError as exc:
        # 2026-10-05: a real video of hers ("Haunted Haul") came back unreadable and the trace keeps only 800 chars --
        # keep the whole reply so the cause is seen, not guessed
        try:
            with open(os.path.join(QDIR, "unreadable_replies.log"), "a", encoding="utf-8") as fh:
                fh.write(f"\n===== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} {exc}\n{reply}\n")
        except OSError:
            pass
        return None


def _note_text() -> str:
    try:
        return open(NOTE, encoding="utf-8").read().strip()
    except OSError:
        return ""


def _plan_text() -> str:
    try:
        return open(PLAN, encoding="utf-8").read().strip()
    except OSError:
        return ""


async def _submit(v: dict, form: str) -> dict:
    """The office asked for `form`; a Long sent back as a Short goes back once (Barry 2026-10-04)."""
    import video_tool
    v.setdefault("format", form)
    if form == "long" and str(v.get("format") or "").strip().lower() != "long":
        return {"fix_this": 'The office asked for a Long video ("format": "long", 8 minutes or more spoken, 1500 words '
                            "or more); this one came back as a Short. Send the Long."}
    return await video_tool.start(AGENT, v)


async def make_one(form: str, slot_label: str, budget_note: str = "", use_plan: bool = True) -> bool:
    """One video turn: she writes it; the office checks it with her tool's own checks and queues it."""
    import video_tool
    if form == "long":
        return await write_long(slot_label)                  # 2026-10-07: in sections, grammar-locked
    before = len(queued())
    # a video Barry asks for gets HIS words, not her week plan beside them (2026-10-07: asked for her intro, she
    # followed the plan and wrote The Green Fairy)
    plan = _plan_text() if use_plan else ""
    made = _recent_made()
    # Barry 2026-10-05 21:40: "I dont want a teaser, now." -- the teaser option is no longer offered.
    # ANY LENGTH (Barry 2026-10-11): the story decides; Short = vertical, Long = widescreen
    length = ("a Short (vertical) -- as long as the story needs" if form == "short"
              else "a Long video (widescreen) -- as long as the story needs")
    msg = (f"Job from the office ({slot_label}): make {length} for your channel, like a film -- every shot directed, "
           f"every picture showing what you are saying. It builds as soon as it is written and lands on Barry's "
           f"DESK; nothing is posted.\n\n"
           + (f"FROM BARRY:\n{_note_text()}\n\n" if _note_text() else "")
           + (budget_note + "\n\n" if budget_note else "")
           + (f"YOUR PLAN FOR THE WEEK (you wrote it):\n{plan}\n\n" if plan else "")
           + ("VIDEOS ALREADY MADE OR WAITING TO BUILD (newest last):\n- " + "\n- ".join(made) + "\n\n" if made else "")
           + "Direct every part yourself: what you say, and what is on screen -- for each part where you are on "
             "screen, a \"shot\" (what you wear and its colour, where you are, what you are doing, how close the "
             "camera is) and, if you want movement, a \"move\"; for every other part the picture, with the plant's "
             "scientific name when one is shown. Call make_video with the whole video -- or, if that is awkward, "
             "write the same fields as one JSON block in your reply (title, format, mood, parts, caption, hashtags).")
    t0 = time.time()
    data = await _ask(msg)
    # FIXES CARRY HER DRAFT (2026-10-07, Barry: "do all three"). Every retry used to start from zero -- a send-back
    # ("334 words, one under") was followed by "your reply had no video", and once she wrote a different video. Now a
    # sent-back video comes back to her WITH the one fix; she changes only that (check_video counts for her).
    for _round in range(3):
        if len(queued()) > before:
            return True                                      # she called make_video; it queued itself
        v = _video_json(data.get("reply") or "")
        if v:
            res = await _submit(v, form)
            if res.get("queued") or res.get("started"):
                return True
            if res.get("fix_this") and not video_tool.last_draft(AGENT, t0):
                video_tool.save_draft(AGENT, v, res["fix_this"])
        d = video_tool.last_draft(AGENT, t0)
        t0 = time.time()
        if d:
            _log(f"{slot_label}: sent back ({str(d.get('fix_this'))[:120]}) -- her draft goes back with the fix")
            data = await _ask("The office checked your video and sent it back for one thing: " + str(d["fix_this"])
                              + "\n\nHere is the draft you sent. Keep everything else as it is and change only that. "
                              "Check it with check_video, then send it with make_video.\n```json\n"
                              + json.dumps(d["draft"], ensure_ascii=False) + "\n```")
        else:
            _log(f"{slot_label}: reply had no video, asking once more (locked). It began: "
                 + " ".join((data.get("reply") or "").split())[:200])
            # 2026-10-07: one grammar-locked pass -- the reply can only be the video
            data = await _ask("Your reply had no video in it, so nothing was queued. Answer with the whole video now "
                              "as JSON: title, format, mood, parts (say, show, shot, plant, motion, move), caption, "
                              "hashtags.", schema=VIDEO_SCHEMA)
            if _json_reply(data) and not _video_json(data.get("reply") or ""):
                data = dict(data, reply="```json\n" + json.dumps(_json_reply(data), ensure_ascii=False) + "\n```")
    if len(queued()) > before:
        return True
    v = _video_json(data.get("reply") or "")
    if v:
        res = await _submit(v, form)
        if res.get("queued") or res.get("started"):
            return True
    _log(f"{slot_label}: no video came back from her turn ({len(data.get('reply') or '')} chars)")
    return False


async def barry_asked(n: int, form: str, ask: str) -> None:
    """Barry's own ask for N new videos (2026-10-11, main.py ASK DOOR). Builds are held while she writes (a build
    would evict Bonsai under her turn); each result is told to him in her window; then builds are released."""
    made = []
    for i in range(1, n + 1):
        hold_builds(120, why="Barry's ask: her writing turns (office)")
        before = queued_titles()
        try:
            ok = await make_one(form, f"Barry's ask, video {i} of {n}",
                                budget_note=f"FROM BARRY, JUST NOW: {ask}", use_plan=False)
        except Exception as exc:  # noqa: BLE001
            ok = False
            _log(f"Barry's ask video {i}: ERROR {type(exc).__name__}: {exc}")
        new = [t for t in queued_titles() if t not in before]
        made += new
        if new:
            note = f"(Office) Video {i} of {n} is written and in the build queue: \"{new[0]}\"."
        else:
            note = (f"(Office) Video {i} of {n} did not queue -- her turn ended without a video that passed the "
                    f"checks. The queue log has the reason (data/video_queue/queue.log).")
        _log(note)
        try:
            memory.log_message(AGENT, "assistant", note)
        except Exception:  # noqa: BLE001
            pass
    release_builds()
    _log(f"Barry's ask done: {len(made)} of {n} queued -- {made}")


def shorts_today() -> int:
    try:
        n = int(memory.get_setting("video_shorts_per_day") or 2)
    except ValueError:
        n = 2
    backlog = len(queued("short"))
    if backlog >= 6:
        return 0
    return min(n, 2) if backlog >= 3 else n


# ------------------------------------------------------------------ redos (2026-10-07)
# Barry: "delete them but I want them redone at some point" / "she redo 1 a week" / "let her redo the names, but tell
# her these are redos". One redo goes into each plan, in docket order; while it is open its plants are let through
# the no-remake check (video_tool.check) -- they are in posted videos -- and it closes when a video with them queues.
def _docket() -> list[dict]:
    try:
        return json.load(open(DOCKET, encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save_docket(d: list[dict]) -> None:
    with open(DOCKET, "w", encoding="utf-8") as fh:
        json.dump(d, fh, indent=1, ensure_ascii=False)


def active_redo() -> dict | None:
    return next((r for r in _docket() if r.get("assigned") and not r.get("done")), None)


def redo_plant_keys() -> set:
    import video_tool
    r = active_redo()
    return {video_tool._plant_key(p) for p in (r or {}).get("plants", [])}


def _assign_redo() -> dict | None:
    d = _docket()
    open_one = next((r for r in d if r.get("assigned") and not r.get("done")), None)
    if open_one:
        return open_one
    week = datetime.date.today().isocalendar()[:2]
    if any(r.get("assigned") and tuple(datetime.date.fromisoformat(r["assigned"]).isocalendar()[:2]) == week
           for r in d):
        return None                                          # this week's redo is already done
    nxt = next((r for r in d if not r.get("assigned")), None)
    if nxt:
        nxt["assigned"] = datetime.date.today().isoformat()
        _save_docket(d)
        _log(f"redo assigned: {nxt['title']}")
    return nxt


def _close_redo(pkg: dict) -> None:
    import video_tool
    d = _docket()
    r = next((x for x in d if x.get("assigned") and not x.get("done")), None)
    if not r:
        return
    keys = {video_tool._plant_key(p) for p in r.get("plants", [])}
    if keys & {video_tool._plant_key(s.get("plant")) for s in pkg.get("scenes") or [] if s.get("plant")}:
        r["done"] = datetime.date.today().isoformat()
        r["new_title"] = pkg.get("title", "")
        _save_docket(d)
        _log(f"redo done: {r['title']} -> '{r['new_title']}'")


def _plan_needs_refresh() -> bool:
    """No plan yet, or 5 videos made since she planned (Barry: "she plans out the next 5 videos")."""
    at = _state().get("plan_at")
    if not at or not os.path.isfile(PLAN):
        return True
    return sum(1 for j in _jobs() if j.get("created", "") >= at) >= PLAN_SIZE


async def plan_week() -> None:
    made = _recent_made()
    redo = _assign_redo()
    msg = ("Scheduled job from the office: plan your next 5 videos. Before you pick, check channel_stats for what is "
           "posted and what people are watching, and list_files for every video you have made; then pick each one "
           "with the steps in your make-video-masterfully skill. For each one: the plant(s), the topic, the hook you "
           "open with, the angle that makes it yours, and your look for your own parts (what you wear, where you "
           "are). This week's Long (8 minutes or more) is made on Saturday night. Write the plan in your reply -- "
           "the office keeps it and hands it back to you each time you make a video."
           + (f'\n\nONE OF THE 5 IS A REDO: "{redo["title"]}" (plants: {", ".join(redo["plants"])}; '
              f'{"a Long" if redo.get("format") == "long" else "a Short"}). Barry: "these are redos. you redo the '
              f'names."' if redo else "")
           + (f"\n\nFROM BARRY:\n{_note_text()}" if _note_text() else "")
           + ("\n\nVIDEOS ALREADY MADE OR WAITING (newest last):\n- " + "\n- ".join(made) if made else ""))
    data = await _ask(msg)
    reply = (data.get("reply") or "").strip()
    if len(reply) < 200:
        _log(f"plan: reply too short to be a plan ({len(reply)} chars) -- keeping last week's")
        return
    os.makedirs(QDIR, exist_ok=True)
    with open(PLAN, "w", encoding="utf-8") as fh:
        fh.write(f"(planned {datetime.date.today():%A %B %d})\n{reply}\n")
    with open(os.path.join(QDIR, f"plan_{datetime.date.today():%Y-%m-%d}.md"), "w", encoding="utf-8") as fh:
        fh.write(reply + "\n")
    st = _state()
    st["plan_at"] = datetime.datetime.now().isoformat()
    _save_state(st)
    _log(f"plan: saved ({len(reply)} chars)")


async def run_slot(what: str, since: datetime.datetime | None = None) -> None:
    label = {"plan": "Sunday planning", "daily": "tonight's videos"}[what]
    if what == "plan":
        await plan_week()
        return
    if _plan_needs_refresh():
        await plan_week()                                    # her 5 are used up (or there is no plan yet)
    wd = datetime.date.today().weekday()
    # RESUMABLE (2026-10-03): a slot cut off by a restart makes only what is still missing -- videos already
    # queued since the slot began count toward it
    done_since = [j for j in _jobs() if since and j.get("created", "") >= since.isoformat()]
    if wd == LONG_NIGHT:
        if not any(j["pkg"].get("format") == "long" for j in done_since):
            ok = await make_one("long", f"{label}, the week's Long")
            _log(f"{label}: long {'queued' if ok else 'missed'}")
        return                                               # a Long night has no room for Shorts
    # SHORTS BY CARD TIME, NOT COUNT (Barry 2026-10-04: "up to 3 minutes, if she does, say a 45 second video, we can
    # do more in a day, maybe 5"): a day's Shorts get a card budget; she chooses full Shorts (~2 h) or 45-60 s
    # teasers (~1 h) and keeps going until it's used, 5 at most
    budget = (SHORTS_BUDGET_SUNDAY if wd == 6 else SHORTS_BUDGET_NIGHT) if shorts_today() else 0
    max_n = min(2 if wd == 6 else MAX_SHORTS_PER_DAY, shorts_today())
    mine = [j for j in done_since if j["pkg"].get("format") == "short"]
    used, n, misses = sum(j.get("estimate_min", 0) for j in mine), len(mine), 0
    while used < budget - 45 and n < max_n and misses < 2:
        left = budget - used
        note = (f"Card time left tonight for your Shorts: about {left} minutes. A full Short (2 to 3 minutes) costs "
                f"about 2 hours of it.")
        before = {j["_file"] for j in _jobs()}
        ok = await make_one("short", f"{label}, Short {n + 1}", note)
        new = [j for j in _jobs() if j["_file"] not in before]
        if ok and new:
            used += new[0].get("estimate_min", 0)
            n += 1
        else:
            misses += 1
        _log(f"{label}: short {n} {'queued' if ok else 'missed'} -- {used}/{budget} min of the Shorts budget")


_active: set[str] = set()                                  # slots started by THIS process


async def cadence_tick() -> None:
    if (memory.get_setting("video_cadence") or "on").lower() == "off":
        return
    now = datetime.datetime.now()
    st = _state()
    for wd, hour, what in SLOTS:
        if now.weekday() != wd:
            continue
        due = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        key = f"{due:%Y-%m-%d %H}:{what}"
        if not (due <= now < due + datetime.timedelta(hours=SLOT_GRACE_H)):
            continue
        if st.get(key) and not (st[key] == "running" and key not in _active):
            continue                                       # done/failed, or running in THIS process
        if st.get(key) == "running":
            _log(f"{key}: resuming after a restart")
        st[key] = "running"
        _save_state(st)
        _active.add(key)
        try:
            await run_slot(what, since=due)
            st[key] = "done"
        except Exception as exc:  # noqa: BLE001
            st[key] = f"failed: {type(exc).__name__}"
            _log(f"{key} failed: {type(exc).__name__}: {exc}")
        _save_state(st)


async def run_video_queue_loop() -> None:
    await asyncio.sleep(240)                                 # let the boot prewarm finish first
    _log("loop started")
    import comfy_image
    try:
        os.remove(comfy_image._REEL_MARK)                    # a restart killed any build that had it up
    except OSError:
        pass
    # a build killed by a restart goes back in the line
    for j in _jobs():
        if j.get("status") == "building":
            j["status"] = "queued"
            _write(j)
            _log(f"re-queued '{j['pkg'].get('title')}' (interrupted by a restart)")
    while True:
        try:
            await cadence_tick()
            await drain_tick()
        except Exception as exc:  # noqa: BLE001
            _log(f"tick error: {type(exc).__name__}: {exc}")
        await asyncio.sleep(CHECK_EVERY_S)
