"""make_video -- an agent makes her OWN video (2026-10-01, Barry: "I want her to make her own video!!!!" /
"I just want the topics the be thought out and the video in 1 2 -3 minut video, not 20-30 scenes").

The agent decides the topic, writes the script, and cuts it into as FEW or as many parts as she likes; each part is
what she says plus what is on screen while she says it (herself, a picture she describes, or a named plant). This
module checks Barry's standing rules RIGHT AWAY (so she fixes it in the same turn -- her words are never edited),
then builds the video in the background with reel_builder (her locked voice, pictures, music -- no captions since 2026-10-06)
and puts the MP4 on Barry's PENDING REVIEW with a download button. Approving sends nothing anywhere (social_post has
no dispatch destination). One build at a time; a render owns the card while it runs.

Barry's rules checked here (from his words, 2026-09-24 .. 2026-10-01):
  short = vertical, 2:00 minimum ("2-3 minutes at least"), 3:00 max (TikTok/Shorts limit)
  long  = widescreen, length is hers ("she can deside on topics and length")
  no "Come closer" stock opener; no "darling"; no cannabis on her channel; no repeat of a recent video's topic
  every plant on screen named (reel_builder's plant rule)
"""
from __future__ import annotations

import asyncio
import datetime
import json
import os
import re
import time
import shutil

import memory

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(_ROOT, "data", "reels", "make_video.log")
WORDS_PER_SECOND = 2.3          # her locked voice incl. pauses, measured on built reels 2026-10-01 (2.21-2.63)
# LONG LENGTH (2026-10-14, Barry: "longs i want at least 8 minutes ... then do 7 minutes"). Her pace on built Longs,
# pauses included, measured the same day: 829 words = 4:27, 578 words = 3:04 -> 3.1 words a second.
LONG_WORDS_PER_SECOND = 3.1
LONG_GOAL_WORDS = 1500          # ~8:04 -- the office keeps asking for chapters until here
LONG_MIN_WORDS = 1310           # ~7:02 -- a Long under this is sent back to write more
_MEDICAL = re.compile(r"\b(lab\s*coat|labcoat|scrubs|stethoscope|doctor'?s?|nurse'?s?|physician|surgeon|"
                      r"medical\s+(coat|gown|uniform|outfit))\b", re.I)
# garments, not accessories (an apron or shawl over the same dress is still one outfit)
_GARMENTS = ("dress", "gown", "blouse", "shirt", "sweater", "cardigan", "jacket", "coat", "cloak", "robe", "skirt",
             "tunic", "vest", "hoodie", "top", "jumpsuit", "kimono", "kaftan", "jeans", "pants", "trousers",
             "leggings", "tee", "t-shirt", "tank", "clothes", "overalls")
TEASER_MIN_WORDS, TEASER_MAX_WORDS = 110, 145      # 45-60 s at her pace (2.21-2.76 w/s)
_lock = asyncio.Lock()
_queued: list[str] = []
_tasks: set = set()

MAKE_VIDEO_TOOL = {
    # 2026-10-01 (video_tool.py): the agent makes her own video, start to finish.
    "type": "function",
    "function": {
        "name": "make_video",
        "description": (
            "Make your own video for your channel: you pick the topic, write the script, and decide how it looks. "
            "Cut the script into parts -- as few or as many as you like (a part can be one line or a whole "
            "paragraph); each part is what you say plus what is on screen while you say it. Your own voice, "
            "music is added for you (no captions on screen), and the finished MP4 goes to your owner's DESK "
            "to watch and download; nothing is posted. CALL THIS TOOL to make the video -- writing the parts out "
            "in your reply makes nothing. format \"short\" = vertical TikTok/Shorts: a full Short of 2 to 3 "
            "or longer -- any length; \"long\" = widescreen YouTube. ANY LENGTH: tell the story at the length "
            "it needs (Barry: \"i dont care how long or short\"), made like a film, every shot directed, every picture "
            "showing what you are saying in that part. "
            "You direct every part. Where YOU are on screen you talk to the camera in your own voice, lips moving "
            "with your words (about 2 minutes of card time per second you are on screen) -- give that part a "
            "\"shot\": what you wear and its colour, where you are, what you are doing, how close the camera is; "
            "a fresh picture of you is made from it (no shot = one of your stock pictures, in your green dress). "
            "Every other part is a still picture that must show exactly what that line says -- set \"motion\": "
            "true on a part to make it move too (about 15 minutes more). Plant pictures take about 10 minutes to "
            "draw, others about 1.5. The tool tells you at once if something needs fixing; then the video waits "
            "in line and builds overnight (Barry's own renders go first)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "format": {"type": "string", "enum": ["short", "long"]},
                "mood": {"type": "string", "enum": ["spooky", "calm", "upbeat", "mystic"],
                         "description": "The music under it."},
                "parts": {
                    "type": "array",
                    "description": "Your script in order.",
                    "items": {"type": "object", "properties": {
                        "say": {"type": "string", "description": "What you say in this part."},
                        "show": {"type": "string",
                                 "description": "\"me\" to be on screen yourself, or describe the picture."},
                        "plant": {"type": "string",
                                  "description": "Scientific name of the plant shown, when the picture shows one."},
                        "shot": {"type": "string",
                                 "description": "For a part where YOU are on screen: the picture of you, in your "
                                                "words -- what you wear and its colour, where you are, what you are "
                                                "doing with your hands, how close the camera is."},
                        "motion": {"type": "boolean",
                                   "description": "true = this part moves (a video clip, about 18 minutes extra). "
                                                  "Your own parts always move."},
                        "move": {"type": "string",
                                 "description": "For a moving part: what happens in the clip, written as a video "
                                                "prompt (your ltx25-prompting skill) -- action, camera, light."},
                        "seconds": {"type": "integer", "minimum": 2, "maximum": 5,
                                    "description": "For a moving part: how long the clip is, 2-5 seconds. Leave it "
                                                   "out and the length of the line decides."},
                        "cutaway": {"type": "array", "items": {"type": "string"},
                                    "description": "For a part where YOU are on screen: pictures to cut to while you "
                                                   "keep talking. You stay on camera for your first sentence; your "
                                                   "next sentences play over these pictures, in order. Describe "
                                                   "each picture like a \"show\"."},
                        "map": {"type": "string",
                                "description": "A MAP CARD instead of a picture: where the plant grows, as places -- "
                                               "countries, regions, continents (\"Mexico, the southwestern United "
                                               "States\"). The office draws the world with that range lighting up and "
                                               "the plant's scientific name on it (give \"plant\" too). Use it once, "
                                               "where you tell where the plant comes from; 2-5 seconds of your line."},
                        "fact": {"type": "string",
                                 "description": "A FACT CARD instead of a picture: one short line, 3-8 words, with "
                                                "its number if it has one (\"Scopolamine 0.2 to 0.6 percent\", "
                                                "\"Used for 3,000 years\") -- shown big over the real plant photo, "
                                                "with the scientific name (give \"plant\"). For the one number or "
                                                "name people must not mishear; 2-5 seconds of your line."},
                        "fx": {"type": "array", "items": {"type": "string"},
                               "description": "EFFECTS over this part, any of: ritual (night grade: purple shadows, "
                                              "grain, vignette), blood (red, crushed blacks), cold (dead blue), "
                                              "flicker (candlelight breathing), glow (bloom on the bright parts), "
                                              "grain, vignette, smoke (purple magic smoke rising), embers, sparks "
                                              "(bursts), lightning (strikes with a flash), sigil (YOUR OWN "
                                              "sigil, drawn in light as you cast it -- give \"sigil\" too). "
                                              "Pick 1-3 that serve the moment; read your skill "
                                              "'effects-and-ritual-visuals'."},
                        "sigil": {"type": ["array", "string"], "items": {"type": "string"},
                                  "description": "Only with fx \"sigil\": YOUR sigil -- the title of a grimoire page that holds it, or SVG path "
                                                 "strings in a 0-100 box (\"M 50 10 L 50 90\", arcs, curves), one "
                                                 "string per stroke -- the office draws each stroke in light, in "
                                                 "order. Only for a spell you are casting; a sigil ON a floor, wall, "
                                                 "altar or book goes into \"show\"/\"shot\" so the picture is drawn "
                                                 "with it."},
                        "grimoire": {"type": "string",
                                     "description": "Show one of YOUR GRIMOIRE PAGES on screen instead of a picture: "
                                                    "its title -- the page appears as a real book page, your sigil "
                                                    "drawn in ink and your words written in. 3-6 seconds of your line."},
                        "sigil_at": {"type": "string", "enum": ["top", "center", "bottom", "left", "right"],
                                     "description": "Where in the frame your cast sigil appears (default center)."}},
                        "required": ["say", "show"]},
                },
                "caption": {"type": "string"},
                "hashtags": {"type": "array", "items": {"type": "string"}},
                "redo_of": {"type": "string",
                            "description": "ONLY when Barry asked you to redo or remake one of your videos: that "
                                           "video's title. Your new version replaces it -- its title, plants and story "
                                           "are allowed again, and the old one is marked replaced (its file is kept)."},
            },
            "required": ["title", "format", "parts", "caption"],
        },
    },
}


CHECK_VIDEO_TOOL = {
    # 2026-10-07 (Barry: "do all three"): her video turns looped re-counting words in her head ("second-guessing in
    # circles", 7+ cuts in one night) and missed windows by one word. The office counts for her; nothing is queued.
    "type": "function",
    "function": {
        "name": "check_video",
        "description": (
            "Check a video BEFORE you send it, with the same fields as make_video. Nothing is made or queued. You "
            "get the exact counts -- total words spoken, about how many seconds that is, how many words are in "
            "your own on-camera parts, the words in each part -- and either \"passes\": true or the one thing to "
            "fix. Use it instead of counting words yourself; when it passes, send the same video with make_video."
        ),
        "parameters": MAKE_VIDEO_TOOL["function"]["parameters"],
    },
}

DRAFT_DIR = os.path.join(_ROOT, "data", "video_queue")

# THE DRAFT WORKSPACE (2026-10-10, Barry: "think deeper and come up with something better or more stable" -> "go,
# build the workspace"). The script lives in a FILE on the office side, not in her reply: she starts a draft, adds
# notes, adds a few parts per short turn, replaces a part by number, checks and sends -- never re-sending the
# whole script. A cut-off turn loses one chunk, not the video. Her words are stored exactly as she wrote them.
VIDEO_DRAFT_TOOL = {
    "type": "function",
    "function": {
        "name": "video_draft",
        "description": (
            "Your video workspace: build a video a few parts at a time instead of writing it all in one breath. "
            "The draft is saved by the office between turns. Actions: "
            "\"start\" (title, format short|long, mood; plus redo_of when Barry asked you to redo a video) "
            "begins a new draft; "
            "\"notes\" (text) saves research notes -- facts with where each came from; "
            "\"add_parts\" (parts: a list of {say, show, shot, plant, motion, move}, same fields as make_video) "
            "appends the next parts in order -- 3 or 4 per turn is right; "
            "\"replace_part\" (n, part) rewrites part number n; \"remove_part\" (n) drops it; "
            "\"status\" shows the draft: parts so far, words so far, words still needed; "
            "\"check\" runs the office's checks on the saved draft and names the one thing to fix; "
            "\"send\" (caption, hashtags) checks it once more and queues it to build -- the finished MP4 lands on "
            "your owner's DESK, nothing is posted; \"discard\" throws the draft away. "
            "Your memory: \"plan\" (title, text) records a video you mean to make later -- it stays in your ledger "
            "until you send that title; \"ledger\" (text = a word to search, or empty for the latest) lists what the "
            "office kept of your work; \"past\" (title) reads a finished or queued script back to you word for word. "
            "Write the words yourself; the office only counts and keeps them."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["start", "notes", "add_parts", "replace_part", "remove_part",
                                                     "status", "check", "send", "discard", "plan", "ledger", "past"]},
                "title": {"type": "string"},
                "format": {"type": "string", "enum": ["short", "long"]},
                "mood": {"type": "string", "enum": ["spooky", "calm", "upbeat", "mystic"]},
                "text": {"type": "string", "description": "For notes: the notes to save."},
                "parts": {"type": "array", "description": "For add_parts: the next parts, in order.",
                          "items": MAKE_VIDEO_TOOL["function"]["parameters"]["properties"]["parts"]["items"]},
                "n": {"type": "integer", "description": "For replace_part / remove_part: the part number (1 = first)."},
                "part": MAKE_VIDEO_TOOL["function"]["parameters"]["properties"]["parts"]["items"],
                "caption": {"type": "string"},
                "hashtags": {"type": "array", "items": {"type": "string"}},
                "redo_of": {"type": "string",
                            "description": "ONLY when Barry asked you to redo or remake one of your videos: that "
                                           "video's title. Your new version replaces it -- its title, plants and story "
                                           "are allowed again, and the old one is marked replaced (its file is kept)."},
            },
            "required": ["action"],
        },
    },
}


def _draft_path(agent_id: str) -> str:
    return os.path.join(DRAFT_DIR, f"draft_{agent_id}.json")


def load_draft(agent_id: str) -> dict | None:
    try:
        with open(_draft_path(agent_id), encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) and d.get("title") else None
    except (OSError, ValueError):
        return None


def _write_draft(agent_id: str, d: dict) -> None:
    os.makedirs(DRAFT_DIR, exist_ok=True)
    d["updated"] = time.time()
    tmp = _draft_path(agent_id) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, _draft_path(agent_id))


def _archive_draft(agent_id: str, why: str) -> None:
    p = _draft_path(agent_id)
    if os.path.isfile(p):
        os.replace(p, os.path.join(DRAFT_DIR, f"draft_{agent_id}_{time.strftime('%Y%m%d_%H%M%S')}_{why}.json"))


def draft_package(d: dict) -> dict:
    """The draft as the make_video package the checks and the builder read."""
    return {"title": d.get("title", ""), "format": d.get("format", "short"), "mood": d.get("mood") or "calm",
            "parts": list(d.get("parts") or []), "caption": d.get("caption") or "", "hashtags": list(d.get("hashtags") or []),
            "redo_of": d.get("redo_of") or ""}


def _floor(form: str) -> int:
    return 0          # ANY LENGTH (Barry 2026-10-11) -- the story is done when she says it is


def draft_status(d: dict) -> dict:
    pkg = draft_package(d)
    c = counts(pkg)
    form = pkg["format"]
    need = max(0, _floor(form) - c["total_words"])
    return {"title": pkg["title"], "format": form, "mood": pkg["mood"], "parts_so_far": len(pkg["parts"]),
            "total_words": c["total_words"], "about_seconds": c["about_seconds"],
            "your_on_camera_words": c["your_on_camera_words"],
            "words_still_needed": need,
            "floor": _floor(form), "notes_words": len(" ".join(d.get("notes") or []).split()),
            "parts": [f"part {i}: {len(str(p.get('say') or '').split())} words -- "
                      f"{'you on camera' if str(p.get('show') or '').strip().lower() in ('me', 'self', 'myself', 'ilnora') else str(p.get('show') or '')[:60]}"
                      for i, p in enumerate(pkg["parts"], 1)]}


def _clean_part(p: dict) -> dict | None:
    if not isinstance(p, dict) or not str(p.get("say") or "").strip():
        return None
    out = {"say": " ".join(str(p["say"]).split()), "show": " ".join(str(p.get("show") or "me").split())}
    for k in ("shot", "plant", "move", "map", "fact", "grimoire"):   # map / fact (10-17), grimoire page (10-19)
        if str(p.get(k) or "").strip():
            out[k] = " ".join(str(p[k]).split())
    if p.get("motion") is True:
        out["motion"] = True
    fx = p.get("fx")                                 # 2026-10-19: her effects (fx.py)
    fx = [fx] if isinstance(fx, str) else (fx if isinstance(fx, list) else [])
    fx = [" ".join(str(x).split()) for x in fx if str(x).strip()]
    if fx:
        out["fx"] = fx
    if p.get("sigil"):                               # 2026-10-19: her own sigil (SVG paths) or a grimoire page title
        sg = p["sigil"]
        out["sigil"] = (" ".join(sg.split()) if isinstance(sg, str) and sg.strip()[:1] not in "Mm"
                        else [str(x) for x in (sg if isinstance(sg, list) else [sg]) if str(x).strip()])
    if p.get("sigil_at"):
        out["sigil_at"] = str(p["sigil_at"]).strip().lower()
    try:                                            # 2026-10-15: clip length, 2-5 s
        if 2 <= int(p.get("seconds")) <= 5:
            out["seconds"] = int(p["seconds"])
    except (TypeError, ValueError):
        pass
    cut = p.get("cutaway")                           # 2026-10-15: pictures she cuts to while she talks
    cut = [cut] if isinstance(cut, str) else (cut if isinstance(cut, list) else [])
    cut = [" ".join(str(c.get("show") if isinstance(c, dict) else c).split()) for c in cut]
    if any(cut):
        out["cutaway"] = [c for c in cut if c]
    return out


def _memory_action(agent_id: str, action: str, a: dict) -> dict:
    """plan / ledger / past -- her memory of what she planned, wrote and made (work_ledger.py)."""
    import work_ledger
    if action == "plan":
        title = str(a.get("title") or "").strip()
        text = str(a.get("text") or "").strip()
        if not title:
            return {"error": 'plan needs a title (the video you mean to make) and text (the angle, in a sentence or two).'}
        work_ledger.note(agent_id, "plan", title, text)
        return {"ok": True, "planned": title, "note": "Saved. It shows in your ledger until you send a video with that title."}
    if action == "ledger":
        rows = work_ledger.search(agent_id, str(a.get("text") or a.get("title") or ""))
        return {"entries": [{"day": work_ledger._day(r["t"]), "kind": r["kind"], "title": r["title"], "text": r["text"]} for r in rows]}
    import video_queue
    title = str(a.get("title") or "").strip()
    j = video_queue.find_made(title) if title else None
    if not j:
        return {"error": f'No written video called "{title}". Use action "ledger" to see the titles you have made.'}
    pk = j.get("pkg") or {}
    script = chr(10).join(f'{i}. {(s.get("narration") or s.get("say") or "").strip()}' for i, s in enumerate(pk.get("scenes") or [], 1))
    return {"title": pk.get("title"), "format": pk.get("format"), "status": j.get("status"), "script_word_for_word": script[:9000],
            "truncated": len(script) > 9000}


async def draft(agent_id: str, a: dict) -> dict:
    """The video_draft tool. Every action answers with the status so she always knows where the draft stands."""
    a = a if isinstance(a, dict) else {}
    action = str(a.get("action") or "status").strip().lower()
    d = load_draft(agent_id)
    if action in ("plan", "ledger", "past"):
        return _memory_action(agent_id, action, a)
    if action == "start":
        title = str(a.get("title") or "").strip()
        form = str(a.get("format") or "").strip().lower()
        if not title or form not in ("short", "long"):
            return {"error": 'start needs a title and format "short" or "long".'}
        # A MADE TITLE IS REFUSED AT START (2026-10-10): she spent 80 minutes on a Long titled "The Flower That Walks
        # Between Worlds" -- made 10-09 -- that the send check was always going to refuse. Same test as check().
        import video_queue
        redo = None
        if str(a.get("redo_of") or "").strip():
            redo = video_queue.find_made(str(a["redo_of"]))
            if not redo:
                return {"error": f'redo_of: there is no made video called "{a["redo_of"]}". Use its exact title.'}
        for old in video_queue.made_titles() + video_queue.queued_titles():
            if redo and old == redo["pkg"].get("title"):
                continue                                 # the video this one replaces (Barry's redo)
            n_t, n_o = _norm(title), _norm(old)
            if min(len(n_t), len(n_o)) >= 8 and (n_t in n_o or n_o in n_t):
                return {"error": f'"{old}" is already made or waiting to build. Barry: "no remakes. all new vids and '
                                 'all new plants". Start a new video: a new plant and a new title.'}
        if d and d.get("parts"):
            _archive_draft(agent_id, "replaced")
        d = {"title": title, "format": form, "mood": str(a.get("mood") or "calm"), "notes": [], "parts": [],
             "created": time.time()}
        if redo:
            d["redo_of"] = redo["pkg"].get("title")
        _write_draft(agent_id, d)
        return {"started": True, "next": "Add your research notes with action \"notes\", then the parts a few at a "
                                         "time with \"add_parts\".", **draft_status(d)}
    if not d:
        return {"error": "No draft yet -- begin with action \"start\" (title, format, mood)."}
    if action == "notes":
        text = " ".join(str(a.get("text") or "").split())
        if not text:
            return {"error": "notes needs text.", **draft_status(d)}
        d.setdefault("notes", []).append(text)
        _write_draft(agent_id, d)
        return {"saved": True, "next": "Now the parts: action \"add_parts\", 3 or 4 at a time, in order.",
                **draft_status(d)}
    if action == "add_parts":
        parts = [q for q in (_clean_part(p) for p in (a.get("parts") or [])) if q]
        if not parts:
            return {"error": "add_parts needs a list of parts, each with say and show.", **draft_status(d)}
        d.setdefault("parts", []).extend(parts)
        _write_draft(agent_id, d)
        st = draft_status(d)
        st["added"] = len(parts)
        st["next"] = ("Keep adding parts until the story is told -- any length (Barry: \"i dont care how long or "
                      "short\"); then action \"check\".")
        return st
    if action in ("replace_part", "remove_part"):
        try:
            n = int(a.get("n"))
        except (TypeError, ValueError):
            return {"error": "give n, the part number (1 = first).", **draft_status(d)}
        parts = d.get("parts") or []
        if not 1 <= n <= len(parts):
            return {"error": f"there is no part {n}; the draft has {len(parts)} parts.", **draft_status(d)}
        if action == "remove_part":
            parts.pop(n - 1)
        else:
            q = _clean_part(a.get("part") or {})
            if not q:
                return {"error": "replace_part needs part: {say, show, ...}.", **draft_status(d)}
            parts[n - 1] = q
        d["parts"] = parts
        _write_draft(agent_id, d)
        return {"done": action, "n": n, **draft_status(d)}
    if action == "status":
        return draft_status(d)
    if action in ("check", "send"):
        if action == "send":
            if str(a.get("caption") or "").strip():
                d["caption"] = " ".join(str(a["caption"]).split())
            if a.get("hashtags"):
                d["hashtags"] = [str(h).strip() for h in a["hashtags"] if str(h).strip()]
            _write_draft(agent_id, d)
        pkg_in = draft_package(d)
        pkg, why = check(agent_id, pkg_in)
        st = draft_status(d)
        if pkg is None:
            return {"passes": False, "fix_this": why, **st}
        if action == "check":
            return {"passes": True, "next": "Send it: action \"send\" with caption and hashtags.", **st}
        if not pkg_in["caption"]:
            return {"passes": True, "error": "send needs a caption (and hashtags).", **st}
        res = await start(agent_id, pkg_in)
        if res.get("queued"):
            _archive_draft(agent_id, "sent")
        return res
    if action == "discard":
        _archive_draft(agent_id, "discarded")
        return {"discarded": True}
    return {"error": f"unknown action {action!r}."}


def counts(a: dict) -> dict:
    """The numbers she needs, from the same parts -> scenes reading check() uses."""
    parts = [p for p in (a.get("parts") or []) if isinstance(p, dict) and (p.get("say") or "").strip()]
    per, me_words = [], 0
    for k, p in enumerate(parts, 1):
        w = len(str(p["say"]).split())
        show = str(p.get("show") or "").strip()
        mine = bool(re.match(r"^(me|self|myself|ilnora)\b", show, re.I)) or (show == "" and not p.get("plant"))
        me_words += w if mine else 0
        per.append(f"part {k}: {w} words{' (you on camera)' if mine else ''}")
    total = sum(len(str(p["say"]).split()) for p in parts)
    return {"total_words": total, "about_seconds": round(total / _wps(a.get("format"))),
            "your_on_camera_words": me_words, "parts": per}


def _wps(form) -> float:
    """Her speaking pace for this format (2026-10-16: she told Barry 11 minutes for a 1,540-word Long that runs ~8.3 --
    the Short pace was used for everything). Longs measured at 3.1 words/s on built videos; Shorts 2.3."""
    return LONG_WORDS_PER_SECOND if str(form or "").strip().lower() == "long" else WORDS_PER_SECOND


# ONE CHECK PER TURN, NEVER THE SAME DRAFT TWICE (2026-10-09, Barry: "she is taking long ass time to think and then
# respond" -> "do those 2 fixes"). Her 16:23 turn ran 22 minutes: two check_video calls on the SAME draft, each one
# making her write the whole script again and think again; 17:03 was three identical checks in 7 minutes. The count
# cannot change until the words do. ContextVar = this request's turn (each chat task starts at 0); the fingerprint
# catches the same draft coming back next turn too. Her words are never touched -- she is only told to rewrite.
import contextvars as _cv
import hashlib as _hashlib
checks_this_turn: _cv.ContextVar[int] = _cv.ContextVar("checks_this_turn", default=0)
_last_check: dict[str, tuple[str, int, float]] = {}        # agent_id -> (draft fingerprint, total words, when)
SAME_DRAFT_WINDOW_S = 3 * 3600


def _draft_fingerprint(a: dict) -> str:
    parts = [str(p.get("say") or "").strip() for p in (a.get("parts") or []) if isinstance(p, dict)]
    raw = (str(a.get("title") or "").strip() + "\n" + "\n".join(parts)).lower()
    return _hashlib.sha1(" ".join(raw.split()).encode("utf-8")).hexdigest()


def check_only(agent_id: str, a: dict) -> dict:
    a = a if isinstance(a, dict) else {}
    fp = _draft_fingerprint(a)
    last = _last_check.get(agent_id)
    if last and last[0] == fp and time.time() - last[2] < SAME_DRAFT_WINDOW_S:
        return {"passes": False, "same_draft": True, "total_words": last[1],
                "fix_this": (f"This is the SAME draft you already checked ({last[1]} words). The count cannot change "
                             f"until the words do -- do not recount it. REWRITE it (to length, or fix the one thing "
                             f"named last time), then check the rewritten video once.")}
    n = checks_this_turn.get()
    if n >= 1:
        return {"passes": False, "one_per_turn": True,
                "fix_this": ("One check per turn. You already used it -- now REWRITE and send the rewritten video "
                             "with make_video; make_video runs the same check and tells you the one thing to fix "
                             "if it still fails.")}
    checks_this_turn.set(n + 1)
    pkg, why = check(agent_id, a)
    c = counts(a)
    _last_check[agent_id] = (fp, int(c.get("total_words") or 0), time.time())
    return {**c, **({"passes": True, "next": "Send this same video with make_video."} if pkg
                    else {"passes": False, "fix_this": why})}


def save_draft(agent_id: str, a: dict, why: str) -> None:
    """A video the office sent back is kept with its one fix, so the next turn fixes THAT draft instead of starting
    over (2026-10-07: every retry started from zero and once wrote a different video)."""
    try:
        with open(os.path.join(DRAFT_DIR, f"last_draft_{agent_id}.json"), "w", encoding="utf-8") as fh:
            json.dump({"at": time.time(), "fix_this": why, "draft": a}, fh, ensure_ascii=False)
    except OSError:
        pass


def last_draft(agent_id: str, since: float) -> dict | None:
    try:
        d = json.load(open(os.path.join(DRAFT_DIR, f"last_draft_{agent_id}.json"), encoding="utf-8"))
        return d if d.get("at", 0) >= since else None
    except (OSError, ValueError):
        return None


def _log(msg: str) -> None:
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


def _recent_titles(agent_id: str, days: int = 14) -> list[str]:
    since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat()
    with memory.get_db() as conn:
        rows = conn.execute("SELECT content FROM approvals WHERE agent_id = ? AND action_type IN ('social_post', "
                            "'file') AND content LIKE 'VIDEO: %' AND created_at >= ? AND status != 'rejected'",
                            (agent_id, since)).fetchall()
    out = []
    for (c,) in rows:
        m = re.match(r"VIDEO: (.+?)(?: \(|\n|$)", c)
        if m:
            out.append(m.group(1).strip())
    try:
        import video_queue
        return out + video_queue.queued_titles()
    except Exception:  # noqa: BLE001
        return out + list(_queued)


def _plant_key(p) -> str:
    """Genus + the start of the species, so "Borago officinale" (her slip) is still borage."""
    w = re.sub(r"[^a-z ]", " ", str(p or "").lower()).split()
    return f"{w[0]} {w[1][:5]}" if len(w) >= 2 else (w[0] if w else "")


def _shingles(text: str) -> set:
    w = re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()).split()
    return {" ".join(w[i:i + 3]) for i in range(len(w) - 2)}


def repeated_parts(says: list[str]) -> list[tuple[int, int]]:
    """[(part, earlier part it repeats)], 1-based: half or more of its 3-word runs already said in an earlier part."""
    sh = [_shingles(s) for s in says]
    out = []
    for i in range(len(says)):
        j = next((j for j in range(i) if len(sh[i]) >= 6 and len(sh[j]) >= 6
                  and len(sh[i] & sh[j]) / min(len(sh[i]), len(sh[j])) >= 0.5), None)
        if j is not None:
            out.append((i + 1, j + 1))
    return out


def _norm(t: str) -> str:
    # 2026-10-07: "Two Witches Sisters Belladonna &amp; Mugwort" slipped past "Two Witches' Sisters: Belladonna &
    # Mugwort" -- the HTML entity left "amp" in. Unescape first; collapse spaces.
    import html
    return " ".join(re.sub(r"[^a-z0-9 ]", "", html.unescape(t or "").lower()).split())


def check(agent_id: str, a: dict) -> tuple[dict | None, str]:
    """(builder package, "") or (None, what to fix)."""
    import reel_builder
    form = str(a.get("format") or "short").strip().lower()
    if form not in ("short", "long"):
        return None, 'format must be "short" or "long".'
    parts = [p for p in (a.get("parts") or []) if isinstance(p, dict) and (p.get("say") or "").strip()]
    if not parts:
        return None, "parts is empty -- give your script as parts, each with what you say and what is on screen."
    scenes = []
    for pn, p in enumerate(parts, 1):
        show = str(p.get("show") or "").strip()
        sc = {"narration": " ".join(str(p["say"]).split()), "_part": pn}   # _part: her numbering, for send-backs
        if p.get("fx"):                             # 2026-10-19: her effects, checked by name before any card time
            import fx as _fx
            _names, _bad = _fx.parse(p["fx"])
            if _bad:
                return None, (f'Part {pn}: "{_bad}" is not an effect the office has. Use any of: '
                              f'{", ".join(_fx.GRADES + _fx.LAYERS)}.')
            if "sigil" in _names:
                _sg = p.get("sigil")
                if isinstance(_sg, str) and _sg.strip() and not _sg.strip()[:1] in "Mm":
                    import grimoire as _gr                 # her sigil by its grimoire page title (2026-10-19)
                    _byname = _gr.sigil_of(agent_id, _sg)
                    if not _byname:
                        return None, (f'Part {pn}: "sigil": "{_sg}" -- your grimoire has no page by that title with '
                                      f'a sigil on it. grimoire action "list" shows your pages.')
                    _sg = _byname
                _paths, _badp = _fx.sigil_paths(_sg)
                if _badp or not _paths:
                    return None, (f'Part {pn}: fx "sigil" needs your own sigil in "sigil": SVG path strings in a '
                                  f'0-100 box, each starting with M (e.g. "M 50 8 L 50 92"). '
                                  + (f'This one is not a path: "{_badp}".' if _badp else "None was given."))
                sc["sigil"] = _paths
                sc["sigil_at"] = p.get("sigil_at") if p.get("sigil_at") in _fx.SIGIL_AT else "center"
            if _names:
                sc["fx"] = _names
        # MAP CARD (2026-10-17, Barry: plan step 1): "map": where the plant grows -> a Hyperframes card scene
        # (reel_builder._card_scene), no picture drawn, never her. The plant name rides as card_plant so the plant
        # engine and the plant label leave the card alone (the card shows the name itself).
        if str(p.get("grimoire") or "").strip():       # 2026-10-19: one of her grimoire pages, shown as a book page
            import grimoire as _gr
            _page = _gr.find(agent_id, p["grimoire"])
            if not _page:
                return None, (f'Part {pn}: "grimoire": "{p["grimoire"]}" -- no page by that title in your grimoire. '
                              f'grimoire action "list" shows your pages.')
            sc["card"] = "grimoire"
            sc["grimoire_page"] = {"title": _page["title"], "text": _page.get("text") or "",
                                   "sigil": list(_page.get("sigil") or [])}
            scenes.append(sc)
            continue
        if str(p.get("map") or "").strip() or str(p.get("fact") or "").strip():
            if str(p.get("map") or "").strip():
                sc["card"] = "map"
                sc["map"] = " ".join(str(p["map"]).split())
            else:                                   # FACT CARD (step 2): one short line, its number, the plant behind
                sc["card"] = "fact"
                sc["fact"] = " ".join(str(p["fact"]).split())
            if str(p.get("plant") or "").strip():
                sc["card_plant"] = " ".join(str(p["plant"]).split())
            try:
                if 2 <= int(p.get("seconds")) <= 5:
                    sc["seconds"] = int(p["seconds"])
            except (TypeError, ValueError):
                pass
            scenes.append(sc)
            continue
        # 2026-10-06: she writes her own parts as "show": "me, leaning in slightly, a borage seed held up..." (with
        # the plant attached) -- that is HER, and the rest of her line is her shot. Read as a picture it went to the
        # plant engine and would draw a stranger instead of her.
        me = re.match(r"^(me|self|myself|ilnora)\b[\s,:;\-–—]*", show, re.I)
        if (show.lower() in ("me", "self", "myself", "ilnora", "") and not p.get("plant")) or (show and me):
            sc["show"] = "self"
            if (p.get("shot") or "").strip():
                sc["shot"] = " ".join(str(p["shot"]).split())
            elif show[me.end():].strip() if me else "":
                sc["shot"] = " ".join(show[me.end():].split())
            if p.get("plant"):                     # 2026-10-14: her shot is drawn with the real plant photo
                sc["plant"] = str(p["plant"]).strip()
        else:
            if p.get("motion") is True:
                sc["motion"] = True
            # a moving picture part keeps its picture (2026-10-03 fix: "move" used to REPLACE the picture
            # description, and the part was dropped from the video for having no picture)
            sc["image_prompt"] = show or str(p.get("plant") or "")
            if p.get("plant"):
                sc["plant"] = str(p["plant"]).strip()
        if (p.get("move") or "").strip():
            sc["motion_prompt"] = " ".join(str(p["move"]).split())
        try:                                        # 2026-10-15: her clip length, 2-5 s (reel_builder._clip_seconds)
            if 2 <= int(p.get("seconds")) <= 5:
                sc["seconds"] = int(p["seconds"])
        except (TypeError, ValueError):
            pass
        # CUTAWAYS (2026-10-15, Barry: "she doesnt have to be on screen her whole time shes talking"). On a part where
        # she is on camera, "cutaway" lists pictures: she stays on camera for her first sentence, and her next sentences
        # play over those pictures, in order -- her words unchanged, only where each sentence is seen.
        cut = p.get("cutaway")
        cut = [cut] if isinstance(cut, str) else (cut if isinstance(cut, list) else [])
        cut = [c for c in (" ".join(str(x.get("show") if isinstance(x, dict) else x).split()) for x in cut) if c]
        sents = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'“‘(])", sc["narration"]) if cut and sc.get("show") == "self" else []
        if len(sents) > 1:
            sc["narration"] = sents[0]
            scenes.append(sc)
            rest, cut = sents[1:], cut[:len(sents) - 1]
            k = len(cut)
            for j, pic in enumerate(cut):
                said = " ".join(rest[round(j * len(rest) / k): round((j + 1) * len(rest) / k)])
                if not said:
                    continue
                cs = {"narration": said, "image_prompt": pic, "cutaway": True, "_part": pn}
                sp = str(p.get("plant") or "").strip()
                if sp and (reel_builder._PLANT_WORDS.search(pic) or sp.split()[0].lower() in pic.lower()):
                    cs["plant"] = sp                # the real species, drawn with its photo as reference
                scenes.append(cs)
            continue
        scenes.append(sc)
    # FREE (2026-10-02, Barry: "not exactly, let her be free, no gate or guide rails right now"). The send-backs for
    # layout (intro/middle/outro), length minimum, opener, words, channel topics and repeats were REMOVED -- her
    # persona still carries his preferences as information. Only the builder's own hard limits remain: a short over
    # 3:00 is rejected by TikTok/Shorts (reel_builder checks it on the real voice), and a picture of a plant must name
    # it so the builder can draw the right species.
    spoken = " ".join(s["narration"] for s in scenes)
    words = len(spoken.split())
    title = str(a.get("title") or "").strip()
    # ANY LENGTH (2026-10-11, Barry: "i dont care how long or short, she does them. if she has a longer story that 2
    # minutes, then shen can freely do it. as long as is presented almost movie production style with every shot.
    # the scenes needs to match the information being told."). The length and on-camera-time send-backs (Short
    # 335-410 / fun fact 69-138 / Long 1950+ / on camera 40-75) are DELETED; the story decides the length. What
    # stays: one outfit, no remakes (redo_of for his redos), plants named, a real picture for every part, and the
    # storyboard check that each picture shows what she is saying.
    # HER LOOK (Barry 2026-10-04 on the first Long: "her clothes were changing too much. And she was in a doctors
    # outfit. I dont want that perception"): no medical clothes, and ONE outfit per video.
    shots = [(n, s.get("shot") or "") for n, s in enumerate(scenes, 1) if s.get("show") == "self"]
    for n, sh in shots:
        if _MEDICAL.search(sh):
            return None, (f'Part {n}: no doctor or medical clothes (lab coat, scrubs, stethoscope, nurse or doctor '
                          'outfits). Barry: "I dont want that perception." Dress as yourself.')
    named = {}
    for n, sh in shots:
        # 2026-10-08: the WHOLE outfit clause, not just the garment type -- "rust-red linen dress" and "green lace
        # dress" both counted as "dress" and passed (Bloodroot). Barry: "fix all that".
        g = " ".join(reel_builder._outfit_of(sh).lower().split())
        if g and any(re.search(rf"\b{w}", g) for w in _GARMENTS):
            named.setdefault(g, n)
    if len(named) > 1:
        parts_list = ", ".join(f"part {n}" for n in sorted(named.values()))
        return None, ("One outfit for the whole video -- Barry: \"her clothes were changing too much.\" Your shots "
                      f"name different clothes ({parts_list}). Name your outfit in your first shot and leave clothes "
                      "out of the others; they keep it.")
    # repeats are checked ONLY against videos made with the talking/animated pipeline (video_queue) -- Barry
    # 2026-10-04: "do the repeat, because im not using the others. these should be new with animation"
    import video_queue
    # REDOS (2026-10-11, Barry: "update the office to not block those videos no more. we are doing redos"). The video
    # named in redo_of is being REPLACED, so its title, plants and script do not count as made for this one; every
    # other video still does. Queuing the redo marks the old job "replaced" (video_queue.enqueue).
    redo = video_queue.find_made(str(a.get("redo_of") or "")) if str(a.get("redo_of") or "").strip() else None
    if str(a.get("redo_of") or "").strip() and not redo:
        return None, f'redo_of: there is no made video called "{a.get("redo_of")}". Use the exact title of the video you are redoing.'
    redo_title = redo["pkg"].get("title") if redo else None
    n_title = _norm(title)
    for old in video_queue.made_titles():
        if old == redo_title:
            continue
        n_old = _norm(old)
        short_one = min(len(n_title), len(n_old))
        if short_one >= 8 and (n_title in n_old or n_old in n_title):
            return None, (f'You already made "{old}" recently. Pick a topic you haven\'t done yet, or a genuinely new '
                          "angle on it with a new title.")
    # NO REMAKES BY CONTENT (2026-10-07, Barry: "no remakes. all new vids and all new plants" -> "do both"). A title
    # is not enough: she retitled one borage script "Sunflower's Cousin" and it passed. Two checks on what is IN it:
    # (1) any plant already in one of her made videos, (2) the same script (word overlap) as a made video.
    new_plants = {_plant_key(s.get("plant")): str(s.get("plant")) for s in scenes if s.get("plant")}
    # THE WEEK'S REDO (2026-10-07, Barry: "she redo 1 a week"): the open redo's plants are in posted videos -- let
    # them through for it (video_queue.redo_plant_keys; closes when a video with them queues)
    redo_keys = video_queue.redo_plant_keys()
    new_words = _shingles(" ".join(s["narration"] for s in scenes))
    for j in video_queue.made_jobs():
        if redo_title and j["pkg"].get("title") == redo_title:
            continue                                     # the video this one replaces
        old_sc = j["pkg"].get("scenes") or []
        old_title = j["pkg"].get("title", "")
        old_keys = {_plant_key(s.get("plant")) for s in old_sc if s.get("plant")}
        used = sorted(new_plants[k] for k in new_plants if k in old_keys and k not in redo_keys)
        if used:
            # which PART (2026-10-10): told only "Atropa belladonna was already in ...", she rewrote the narration
            # of parts 20 and 45 for four turns; the plant was part 28's on-screen "plant" field.
            where = [i + 1 for i, s in enumerate(scenes)
                     if s.get("plant") and _plant_key(s.get("plant")) in old_keys and _plant_key(s.get("plant")) not in redo_keys]
            return None, (f'{", ".join(used)} was already in "{old_title}" -- it is the on-screen plant of '
                          f'{", ".join("part " + str(n) for n in where)}. Barry: "no remakes. all new vids and all '
                          'new plants" / "there are thousands of plants she knows, tell her to get creative" -- every '
                          'plant in this video has to be one you have not made a video about yet. Change that part\'s '
                          '"plant" (and its picture) to a plant you have not made a video about; mentioning a relative '
                          'in what you SAY is fine.')
        old_words = _shingles(" ".join(s.get("narration", "") for s in old_sc))
        if new_words and old_words and len(new_words & old_words) / max(1, min(len(new_words), len(old_words))) > 0.35:
            return None, (f'This is the same script as "{old_title}", which you already made. Barry: "no remakes. all '
                          'new vids and all new plants" -- write a new video.')
    # NO PART SAID TWICE (2026-10-10): her Long "The Sacred Thornapple" had parts 7 and 11 word for word the same, and
    # near-copies at 3/9, 5/26, 29/47, 30/33, 36/37 -- stalled turns re-added chapters. The viewer would hear the same
    # lines twice (Barry: "the script needs to be dope. almost production level").
    dups = repeated_parts([s["narration"] for s in scenes])
    if dups:          # ALL of them in one send-back -- one-per-round cost her an hour of check turns (2026-10-10)
        return None, ("These parts say the same thing as an earlier part, so the viewer would hear it twice: "
                      + "; ".join(f"part {a} repeats part {b}" for a, b in dups)
                      + ". Remove the repeats (video_draft action \"remove_part\", highest number first so the others "
                        "keep their numbers) or rewrite them to say something new, then check again.")
    # NO LINE SAID TWICE (2026-10-16, Barry: "make sure she doesnt say repeated lines within the video"). The part check
    # above misses one sentence repeated inside two different parts; this catches any sentence of 6+ words whose
    # wording is mostly already said elsewhere in the video.
    sents = []
    for n, s in enumerate(scenes, 1):
        for t in re.split(r"(?<=[.!?])\s+", s["narration"]):
            if len(t.split()) >= 6:
                sents.append((n, t.strip(), _shingles(t)))
    said_twice = []
    for si in range(len(sents)):
        sj = next((sj for sj in range(si) if sents[si][2] and sents[sj][2]
                   and len(sents[si][2] & sents[sj][2]) / min(len(sents[si][2]), len(sents[sj][2])) >= 0.6), None)
        if sj is not None:
            said_twice.append((sents[sj][0], sents[si][0], sents[si][1]))
    if said_twice:
        return None, ("These lines are said twice in the video -- Barry: \"make sure she doesnt say repeated lines within "
                      "the video\": " + "; ".join(f'part {y} repeats part {x}: "{t[:90]}"' for x, y, t in said_twice[:8])
                      + ". Say it once. An ending that echoes your opening is good -- in new words, not the same line. "
                        "Fix those parts (video_draft action \"replace_part\"), then check again.")
    # LONG LENGTH (2026-10-14, Barry: "longs i want at least 8 minutes, if she cant handle that ot the ltx or comfy cand
    # do that long then do 7 minutes"). After the repeat check, so only words the viewer hears once count.
    if form == "long" and words < LONG_MIN_WORDS:
        return None, (f"This Long is {words} words -- about {words / LONG_WORDS_PER_SECOND / 60:.1f} minutes spoken. "
                      f"Barry: \"longs i want at least 8 minutes\" -- about {LONG_GOAL_WORDS} words; 7 minutes "
                      f"({LONG_MIN_WORDS} words or more spoken) at the very least. Carry the story further: write the "
                      f"next chapter(s) with video_draft action \"add_parts\", then check again.")
    # A PICTURE PART NEEDS A PICTURE (2026-10-06): "show": "motion" with no description drew strangers jogging
    # nobody asked for. A one- or two-word "show" with no "move" text to draw
    # from goes back before any card time.
    # SEND-BACKS NAME HER PART, NOT THE SCENE (2026-10-18): a cutaway splits one of her parts into several scenes, so
    # "Part(s) [3]" pointed at part 2's first cutaway picture -- she rewrote part 3 three times and it never cleared.
    def _labels(idx: list[int]) -> str:
        seen = []
        for i in idx:
            s = scenes[i - 1]
            lab = f"part {s.get('_part', i)}" + (" (a cutaway picture)" if s.get("cutaway") else "")
            if lab not in seen:
                seen.append(lab)
        return ", ".join(seen)
    blank = [i + 1 for i, s in enumerate(scenes) if s.get("show") != "self" and not s.get("plant")
             and not reel_builder._is_card(s)        # a map card is its own picture (2026-10-17)
             and len(reel_builder._picture_text(s).split()) <= 2]
    if blank:
        return None, (f'{_labels(blank)}: no picture described -- "show" is a description of what is on screen '
                      '(or "me" for you). Describe each picture in a full sentence.')
    unnamed = reel_builder._unnamed_plant_scenes(scenes)
    if unnamed:
        return None, (f"{_labels(unnamed)}: a plant is shown without its name. A cutaway picture takes the "
                      f'"plant" of the part it belongs to -- give that part "plant": "<scientific name>". '
                      "If a picture description uses any of: "
                      "herb, plant, leaf, leaves, flower, blossom, petal, sprig, weed, seedling, stem, bud, shrub, "
                      'bush, vine, root, bark -- give that part "plant": "<scientific name>", or describe the '
                      "picture without those words.")
    for sc in scenes:
        sc.pop("_part", None)                       # the send-backs' marker; the builder never sees it
    pkg = {"title": title or "untitled", "mood": a.get("mood") or "mystic", "voice_agent": agent_id,
           "format": form, "scenes": scenes, "caption": str(a.get("caption") or ""),
           "hashtags": [str(h) for h in (a.get("hashtags") or [])],
           # Barry 2026-10-02: "ilnora has to have life" -- her parts are animated (reel_builder MOTION)
           "motion": True}
    if redo_title:
        pkg["redo_of"] = redo_title
    return pkg, ""


async def _build(agent_id: str, pkg: dict, storyboard=None) -> str | bool:
    import agent_files
    import reel_builder
    async with _lock:                                   # one video at a time on the card
        _log(f"{agent_id}: building '{pkg['title']}' ({pkg['format']}, {len(pkg['scenes'])} parts)")
        try:
            res = await reel_builder.build_reel(pkg, log=lambda s: _log(f"  {s}"), storyboard=storyboard)
        except Exception as exc:  # noqa: BLE001
            res = {"ok": False, "why": f"{type(exc).__name__}: {exc}"}
        finally:
            if pkg["title"] in _queued:
                _queued.remove(pkg["title"])
        if not res.get("ok"):
            _log(f"{agent_id}: FAILED '{pkg['title']}': {res.get('why')}")
            memory.queue_for_approval(agent_id, "social_post",
                                      f"VIDEO FAILED: {pkg['title']}\nThe builder said: {res.get('why')}")
            return False
        d = agent_files._agent_dir(agent_id)
        os.makedirs(d, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9 _-]+", "", pkg["title"]).strip().replace(" ", "_")[:60] or "video"
        dest = os.path.join(d, f"{safe}_{os.path.basename(res['video'])}")
        shutil.copy2(res["video"], dest)
        text = (f"VIDEO: {pkg['title']} ({res.get('format')}, {res.get('seconds')} s)\n"
                f"Caption: {pkg['caption']}\nHashtags: {' '.join(pkg['hashtags'])}\n"
                + (f"Music: {res.get('music_credit')}\n" if res.get("music_credit") else ""))
        # ON HIS DESK WITH DOWNLOAD (Barry 2026-10-01: "on my desk, Ilnora doesnt have a read or download button
        # ... i need easy and quick access to the videos, so i can upload them"). The DESK only gives a download
        # button to action_type 'file' rows (agent_files.list_agent_files), delivered = status approved -- the
        # same delivery agent_files.write_file uses for documents. Nothing is posted anywhere.
        aid = memory.queue_for_approval(agent_id, "file", text, file_path=dest)
        if aid:
            with memory.get_db() as conn:
                conn.execute("UPDATE approvals SET status = 'approved' WHERE id = ?", (aid,))
        _log(f"{agent_id}: DONE '{pkg['title']}' {res.get('seconds')} s in {res.get('build_seconds')} s -> card {aid}")
        return dest                                     # truthy: the delivered MP4 (video_queue copies it to his folder)


async def start(agent_id: str, a: dict) -> dict:
    pkg, why = check(agent_id, a if isinstance(a, dict) else {})
    if pkg is None:
        save_draft(agent_id, a if isinstance(a, dict) else {}, why)
        return {"started": False, "fix_this": why, **counts(a if isinstance(a, dict) else {})}
    # QUEUED, BUILT OVERNIGHT (2026-10-03, Barry: "over night" / "sunday is when we can get a bunch of videos
    # done"): video_queue builds it in the next render window; Barry's and Elliot's renders go first.
    import video_queue
    q = video_queue.enqueue(agent_id, pkg)
    words = sum(len(s["narration"].split()) for s in pkg["scenes"])
    return {"queued": True, "title": pkg["title"], "parts": len(pkg["scenes"]),
            "about_seconds_long": round(words / _wps(pkg.get("format"))),
            "card_minutes_about": q["card_minutes_about"], "videos_ahead_of_it": q["videos_ahead"],
            "result": "It is in line and builds as soon as the card is free (Barry's own renders go first). When it is "
                      "done it lands on your owner's DESK with a download button. Nothing is posted."}
