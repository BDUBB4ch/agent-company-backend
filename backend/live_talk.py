"""LIVE CONVERSATIONS (2026-10-15). Barry: "yes, live conversations, any time" / "taliyah personal only, and yes i want
to jump in. I dont want it to happen on a schedule. I want it to be, if they want to talk to someone, or if i want them
too, like Amara and Priya."

Two or more of them talk turn by turn until it is settled -- each line a real turn by that agent, in their own words
(never rewritten). Nothing here picks who talks or what about: a talk starts ONLY when an agent calls talk_with (their
choice) or Barry starts one (his ask, a dashboard button). No schedule, any hour.

  work      -- each line runs through /api/chat as an office task turn: their full persona, brain and TOOLS.
  personal  -- off the clock, the home/phone setup social.py uses (personality first, no business). Taliyah is ALWAYS
               personal (Barry: "taliyah personal only").

Barry can jump in at any point (say()); his line lands in the transcript and the next speaker hears it. A talk ends
when one of them closes it ([DONE]) and the others have had a last word, at MAX_TURNS, or when Barry stops it.
One talk at a time (one Bonsai slot); between lines it waits for Barry's own chats, any render, and Ilnora's video build
("if she isnt finish, the office has to wait"). Afterwards every participant remembers it: work talks in a monthly
on-demand doc on their shelf (live-talks-YYYY-MM.md), personal ones in the same per-pair DM journal their calls use.
State: data/live_talks/<id>.json. Dashboard: AgentDashboard/live-talks.html."""
from __future__ import annotations

import asyncio
import datetime
import json
import os
import re
import time
import uuid

import httpx

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(_ROOT, "data", "live_talks")
LOG = os.path.join(DIR, "live_talks.log")
MAX_TURNS = 16
LINE_TIMEOUT_S = 1800
TALIYAH = "taliyah"
DONE = re.compile(r"\[\s*DONE\s*\]", re.I)


def _log(msg: str) -> None:
    os.makedirs(DIR, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


def _path(tid: str) -> str:
    return os.path.join(DIR, f"{tid}.json")


def _load(tid: str) -> dict | None:
    try:
        return json.load(open(_path(tid), encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save(t: dict) -> None:
    os.makedirs(DIR, exist_ok=True)
    tmp = _path(t["id"]) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(t, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, _path(t["id"]))


def talks(limit: int = 20) -> list[dict]:
    if not os.path.isdir(DIR):
        return []
    out = [x for x in (_load(f[:-5]) for f in os.listdir(DIR) if f.endswith(".json")) if x]
    return sorted(out, key=lambda x: x.get("created", 0), reverse=True)[:limit]


def current() -> dict | None:
    """The talk running now, else the oldest one waiting, else None."""
    ts = talks(50)
    run = [x for x in ts if x.get("status") in ("running", "stopping")]
    if run:
        return run[0]
    q = sorted((x for x in ts if x.get("status") == "queued"), key=lambda x: x.get("created", 0))
    return q[0] if q else None


def _first(aid: str) -> str:
    import reflect
    return reflect.HUMAN_NAMES.get(aid, aid.title())


def resolve(name: str) -> str | None:
    """A first name, office name or agent id -> agent id (anyone on the social roster, hires included)."""
    import social
    n = (name or "").strip().lower().lstrip("@")
    if not n:
        return None
    for aid in social.social_roster():
        if n in (aid.lower(), _first(aid).lower()):
            return aid
    try:
        from agents import AGENTS
        for aid, a in AGENTS.items():
            if n == str(a.get("office_name", "")).lower():
                return aid
    except Exception:  # noqa: BLE001
        pass
    return None


def start(started_by: str, agent_ids: list[str], about: str, kind: str = "work") -> dict:
    """Queue a talk. started_by: an agent id, or "barry". Returns the talk or {"error"}."""
    import social
    roster = set(social.social_roster())
    ids = []
    for a in agent_ids:
        if a and a not in ids:
            ids.append(a)
    bad = [a for a in ids if a not in roster]
    if bad:
        return {"error": f"not on the roster: {', '.join(bad)}"}
    if len(ids) < 2:
        return {"error": "a live conversation needs at least two of them"}
    kind = "personal" if (TALIYAH in ids or str(kind).lower().startswith("pers")) else "work"
    for x in talks(50):
        if x.get("status") in ("queued", "running") and set(x.get("agents") or []) == set(ids):
            return x                                       # already happening -- no duplicate
    t = {"id": f"{datetime.datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:4]}", "agents": ids,
         "names": [_first(a) for a in ids], "about": " ".join(str(about or "").split())[:600], "kind": kind,
         "started_by": started_by, "status": "queued", "created": time.time(), "turns": [], "barry_pending": []}
    _save(t)
    _log(f"queued {t['id']}: {' + '.join(t['names'])} ({kind}) about {t['about'][:80]!r} -- started by {started_by}")
    return t


def say(tid: str, text: str) -> dict:
    """Barry jumps in."""
    t = _load(tid)
    text = " ".join(str(text or "").split())
    if not t or not text:
        return {"error": "no such talk or nothing to say"}
    if t.get("status") not in ("queued", "running"):
        return {"error": "that conversation is over"}
    t["barry_pending"] = (t.get("barry_pending") or []) + [text]
    _save(t)
    return {"ok": True}


def stop(tid: str) -> dict:
    t = _load(tid)
    if not t:
        return {"error": "no such talk"}
    if t.get("status") == "queued":
        t["status"] = "stopped"
    elif t.get("status") == "running":
        t["status"] = "stopping"
    _save(t)
    return {"ok": True, "status": t["status"]}


async def _wait_turn() -> None:
    """Barry's own chats, any render, and Ilnora's video build go first."""
    import comfy_image
    import ideation
    while ideation._active_chat_count > 0 or ideation._video_building() or comfy_image.render_in_progress():
        await asyncio.sleep(15)


def _rendered(turns: list[dict]) -> str:
    return "\n\n".join(f"{x['who']}: {x['text']}" for x in turns) or "(nobody has said anything yet)"


def _others(t: dict, aid: str) -> list[str]:
    return [_first(a) for a in t["agents"] if a != aid]


async def _work_line(t: dict, aid: str, closing: bool) -> tuple[str, list]:
    me, others = _first(aid), _others(t, aid)
    who = ", ".join(others) + (" and Barry" if any(x["who"] == "Barry" for x in t["turns"]) else "")
    starter = "Barry" if t["started_by"] == "barry" else _first(t["started_by"])
    msg = (f"[live conversation] You are in a LIVE CONVERSATION right now with {who}, at work. {starter} started it, "
           f"about: {t['about'] or '(no topic given)'}. Barry can read it and may join in.\n\n"
           f"The conversation so far:\n\n{_rendered(t['turns'])}\n\n"
           f"You are {me}. Say your next line to them -- only what you say, in your own voice, talking, not a report. "
           "Use your tools if the conversation needs them. "
           + ("They are wrapping up: say your last word. " if closing else
              "When it is settled and you have nothing to add, end your line with [DONE]. "))
    async with httpx.AsyncClient(timeout=LINE_TIMEOUT_S) as cx:
        r = await cx.post("http://127.0.0.1:8420/api/chat",
                          json={"agent_id": aid, "message": msg, "task": True, "personal": False,
                                "activity": f"live talk with {', '.join(others)}"})
    r.raise_for_status()
    data = r.json() or {}
    return str(data.get("reply") or ""), list(data.get("tool_calls") or [])


async def _personal_line(t: dict, aid: str, closing: bool, get_agent_fn) -> str:
    import llm_router
    import memory
    import social
    agent = get_agent_fn(aid)
    if not agent:
        return ""
    me, others = _first(aid), _others(t, aid)
    starter = "Barry" if t["started_by"] == "barry" else _first(t["started_by"])
    own = social._home_of(agent["office_name"])
    setting = ("## A LIVE CONVERSATION, OFF THE CLOCK\n"
               f"You and {', '.join(others)} are talking right now -- not work. "
               + (f"Barry asked you to talk{(' about: ' + t['about']) if t['about'] else ''}. " if starter == "Barry"
                  else (f"You wanted to talk{(' about: ' + t['about']) if t['about'] else ''}. " if starter == me
                        else f"{starter} wanted to talk{(' about: ' + t['about']) if t['about'] else ''}. "))
               + "Barry can read this and may join in."
               + (f"\n\nYour place, as you yourself described it:\n{own}" if own else ""))
    backend, model = memory.get_active_generation()
    mdl = social._resolve_model(aid, backend, model)
    opinions = {o: social._opinion_of(agent["office_name"], o) for o in others}
    prompt = (f"The conversation so far:\n\n{_rendered(t['turns'])}\n\nYou are {me}. Say your next line."
              + (" They are wrapping up: say your last word." if closing else
                 " When you have both said what you wanted to, end your line with [DONE]."))
    reply = await social._talk_generate(llm_router, backend,
                                        social._social_system(agent, me, setting, backend, mdl, opinions, aid),
                                        [{"role": "user", "content": prompt}], model=mdl, use_tools=False,
                                        office_name=agent["office_name"])
    return str(reply or "")


def _clean(reply: str, me: str, prior: list[str]) -> tuple[str, bool]:
    import social
    done = bool(DONE.search(reply or ""))
    said = social._own_lines(DONE.sub("", reply or ""), me, prior)
    return said.strip(), done


def _remember(t: dict, get_agent_fn) -> None:
    import memory
    import reflect
    import social
    from agents import AGENTS
    if len([x for x in t["turns"] if x["who"] != "Barry"]) < 2:
        return
    today, month = datetime.date.today().isoformat(), datetime.date.today().isoformat()[:7]
    stamp = datetime.datetime.now().strftime("%I:%M %p").lstrip("0")
    head = (f"\n\n[{today} {stamp}] live conversation -- {' + '.join(t['names'])}"
            + (f" (Barry joined)" if any(x["who"] == "Barry" for x in t["turns"]) else "")
            + (f", about: {t['about']}" if t["about"] else ""))
    block = head + "\n" + _rendered(t["turns"])

    def office(aid):
        a = get_agent_fn(aid) or AGENTS.get(aid)          # the live roster, hires included
        return (a or {}).get("office_name")

    for aid in t["agents"]:
        off = office(aid)
        if not off:
            continue
        if t["kind"] == "personal":           # the same per-pair journal their calls write
            for other in t["agents"]:
                if other == aid:
                    continue
                fo = _first(other)
                sn = f"mind-dm-{fo.lower()}-{month}.md"
                existing = social._fact_content(off, sn) or f"DM THREAD with {fo} -- {month}"
                joined = existing + block
                if len(joined) > social.DM_JOURNAL_CAP:
                    joined = joined[:200] + "\n[...older messages trimmed...]\n" + joined[-(social.DM_JOURNAL_CAP - 250):]
                reflect._store(off, sn, f"DMs with {fo} -- {month}", joined)
        else:                                 # an on-demand doc on their shelf, found when it matters
            sn = f"live-talks-{month}.md"
            names = sorted({n for x in talks(200) if x.get("kind") == "work" and aid in (x.get("agents") or [])
                            for n in x.get("names") or []} | set(t["names"]))
            existing = social._fact_content(off, sn)
            if not existing:
                existing = (f"LIVE TALKS -- {month}\nUSE WHEN: live talk, live conversation, we talked, talked with, "
                            f"what did we agree, what we decided, " + ", ".join(n.lower() for n in names) + "\n"
                            "Your live conversations at work this month, word for word.")
            reflect._store(off, sn, f"Live talks -- {month}", existing + block)
    if t["kind"] == "personal":
        try:
            import relationships
            relationships.record_scene(list(t["agents"]), weight=1.0)
        except Exception:  # noqa: BLE001
            pass


async def _run(t: dict, get_agent_fn) -> None:
    t["status"], t["started"] = "running", time.time()
    _save(t)
    _log(f"start {t['id']}")
    order, n, closing, last_word = list(t["agents"]), 0, False, []
    while n < MAX_TURNS:
        t = _load(t["id"]) or t
        if t.get("status") == "stopping":
            break
        for line in t.get("barry_pending") or []:
            t["turns"].append({"who": "Barry", "text": line, "at": time.time()})
        t["barry_pending"] = []
        if closing:
            if not last_word:
                break
            aid = last_word.pop(0)
        else:
            aid = order[n % len(order)]
        _save(t)
        await _wait_turn()
        me = _first(aid)
        prior = [x["text"] for x in t["turns"]]
        try:
            if t["kind"] == "work":
                reply, tools = await _work_line(t, aid, closing)
            else:
                reply, tools = await _personal_line(t, aid, closing, get_agent_fn), []
        except Exception as exc:  # noqa: BLE001
            _log(f"{t['id']}: {me}'s line failed ({type(exc).__name__}: {exc}) -- ending")
            break
        if not reply or reply.lstrip().startswith("["):
            _log(f"{t['id']}: {me} returned nothing usable -- ending")
            break
        said, done = _clean(reply, me, prior)
        if not said:
            break
        t = _load(t["id"]) or t
        t["turns"].append({"who": me, "agent_id": aid, "text": said, "at": time.time(),
                           **({"tools": tools} if tools else {})})
        _save(t)
        n += 1
        if done and not closing:
            closing = True
            last_word = [a for a in order if a != aid]
    t = _load(t["id"]) or t
    t["status"] = "stopped" if t.get("status") == "stopping" else "done"
    t["finished"] = time.time()
    _save(t)
    try:
        _remember(t, get_agent_fn)
    except Exception as exc:  # noqa: BLE001
        _log(f"{t['id']}: remembering failed ({type(exc).__name__}: {exc})")
    _log(f"{t['status']} {t['id']}: {len(t['turns'])} lines in {(t['finished'] - t['started']) / 60:.0f} min")


async def run_live_talk_loop(get_agent_fn) -> None:
    """Runs queued talks one at a time. Never starts one by itself."""
    for x in talks(50):                        # a restart killed whatever was running: finish its record
        if x.get("status") in ("running", "stopping"):
            x["status"] = "interrupted"
            _save(x)
    while True:
        try:
            q = sorted((x for x in talks(50) if x.get("status") == "queued"), key=lambda x: x.get("created", 0))
            if q:
                await _run(q[0], get_agent_fn)
        except Exception as exc:  # noqa: BLE001 -- a loop must never die
            _log(f"loop error: {type(exc).__name__}: {exc}")
        await asyncio.sleep(10)
