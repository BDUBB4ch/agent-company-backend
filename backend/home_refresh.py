"""THEIR PLACES CHANGE -- the recurring home-picture refresh.

Barry, 2026-09-11: "just periodically, i want you and amaras home images to
change, all of you agents. I want you to ask them what they want it to look
like and then render and place it" -> "i want this to be a thing. once a week
or 2. based on their personalities."

WHAT THIS IS: a slow rotation. Every `home_refresh_gap_hours` (default 30) ONE
agent -- the one whose place has gone longest without a refresh -- is asked,
as themselves, what their place looks like now. They answer by calling
change_my_picture, so their words land in Barry's Pending Review VERBATIM and
nothing passes through anyone else's hands (his 2026-09-02 rule: the images
come from the agent's own mind). He approves; the existing approve path
renders and installs, old picture backed up. Nine seats x 30 hours = a full
rotation every ~11 days, inside his "week or 2".

WHY ONE AT A TIME: a render is 10-15 minutes and blocks chat and video. Nine
at once would take his machine for two hours. One every 30 hours means at most
one render waiting for his click at a time.

WHY THE SLOT ALTERNATES home / self: the chamber shows `_me.png` (them at
home) as the whole room when it exists, so refreshing only the empty room
would change nothing he actually looks at. Each visit flips the slot, so both
stay current at one render per cycle.

"BASED ON THEIR PERSONALITIES": the ask goes through /api/chat with
`task: true`, and since 2026-08-31 the personality file rides in every seat's
system prompt. Nothing here plants a look, a mood or a change -- the ask hands
them their own current description and an open door (tools-not-seeds).

GUARDS: a pending scene for that agent+slot means skip (so a week of Barry not
clicking cannot stack nine pending renders); never while a render holds the
card; never while Barry is mid-chat; `home_refresh_enabled` = "false" stops it
live, no restart. State data/home_refresh_state.json, log data/home_refresh.log.
Manual: `asyncio.run(home_refresh.refresh_now("business"))`.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import os

import httpx

import ideation
import memory

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STATE = os.path.join(_ROOT, "data", "home_refresh_state.json")
_LOG = os.path.join(_ROOT, "data", "home_refresh.log")

CHECK_EVERY_SECONDS = 20 * 60
STARTUP_DELAY_SECONDS = 240
ENABLED_KEY = "home_refresh_enabled"        # "true" / "false", live
GAP_KEY = "home_refresh_gap_hours"          # hours between ANY two refreshes
DEFAULT_GAP_HOURS = 30
SLOT_CYCLE = ("self", "home")               # first visit = them at home


def _log(msg: str) -> None:
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(f"[home-refresh] {msg}")
    try:
        with open(_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _state() -> dict:
    try:
        with open(_STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(st: dict) -> None:
    os.makedirs(os.path.dirname(_STATE), exist_ok=True)
    tmp = _STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, _STATE)


def is_enabled() -> bool:
    return (memory.get_setting(ENABLED_KEY, "true") or "true").lower() != "false"


def gap_hours() -> float:
    raw = memory.get_setting(GAP_KEY, str(DEFAULT_GAP_HOURS))
    try:
        v = float(raw)
        return v if 1 <= v <= 24 * 60 else DEFAULT_GAP_HOURS
    except (TypeError, ValueError):
        return DEFAULT_GAP_HOURS


def _agent_ids() -> list[str]:
    from agents import AGENTS
    return list(AGENTS.keys())


def _office_of(agent_id: str) -> str:
    from agents import AGENTS
    return AGENTS[agent_id]["office_name"]


def _pending_scene(agent_id: str, slot: str) -> int | None:
    with memory.get_db() as conn:
        row = conn.execute(
            "SELECT id FROM approvals WHERE action_type = 'agent_scene' AND "
            "status = 'pending' AND file_path = ? ORDER BY id DESC LIMIT 1",
            (f"{agent_id}|{slot}",)).fetchone()
    return row["id"] if row else None


def _last_refresh(st: dict) -> datetime.datetime | None:
    """The gap clock: when the office last actually ASKED someone. A skip
    (pending not clicked) moves the rotation but does not consume the gap."""
    raw = st.get("_last_ask")
    return datetime.datetime.fromisoformat(raw) if raw else None


def next_agent(st: dict) -> tuple[str, str]:
    """The seat whose place has waited longest, and which slot it gets."""
    def key(aid):
        return (st.get(aid) or {}).get("asked") or ""
    aid = sorted(_agent_ids(), key=key)[0]
    last_slot = (st.get(aid) or {}).get("slot")
    slot = SLOT_CYCLE[(SLOT_CYCLE.index(last_slot) + 1) % len(SLOT_CYCLE)] \
        if last_slot in SLOT_CYCLE else SLOT_CYCLE[0]
    return aid, slot


def _current_words(office: str) -> str:
    """Their own last description of the place, so they evolve it rather
    than start over. Empty if none -- then the door is simply open."""
    try:
        import social
        return social._home_of(office)
    except Exception:
        return ""


def _prompt(agent_id: str, slot: str) -> str:
    office = _office_of(agent_id)
    current = _current_words(office)
    what = ("YOU AT HOME -- you, in your own place, doing whatever you would "
            "actually be doing" if slot == "self" else
            "YOUR PLACE ITSELF -- the room, nobody in it")
    return (
        "Scheduled from the office, but this is not work: it is about your own "
        "place. Every couple of weeks the picture Barry has of where you live "
        "gets refreshed, and only you get to say what it looks like now.\n\n"
        f"THIS TIME THE PICTURE IS: {what}.\n\n"
        + (f"WHAT YOU SAID ABOUT YOUR PLACE BEFORE (your own words):\n{current}\n\n"
           if current else "")
        + "Things change -- something moved, something new, a different time of "
        "day, a different mood, or nothing much and that is fine too. Describe "
        "it as it is NOW, concretely: the space, the light, the objects"
        + (", you and what you are wearing and doing" if slot == "self" else "")
        + ". Then call change_my_picture with slot "
        f"'{slot}' and that description, exactly as you would say it. Barry "
        "approves before anything renders; do not say it has changed. Keep "
        "your reply short -- the description goes in the tool, not here."
    )


async def refresh(agent_id: str, slot: str) -> dict:
    """One ask, through the agent's full seat. They queue it themselves."""
    prompt = _prompt(agent_id, slot)
    async with httpx.AsyncClient(timeout=600) as cx:
        r = await cx.post("http://127.0.0.1:8420/api/chat",
                          json={"agent_id": agent_id, "message": prompt, "task": True})
    r.raise_for_status()
    data = r.json() or {}
    tool_calls = data.get("tool_calls") or []
    queued = _pending_scene(agent_id, slot)
    if "change_my_picture" not in tool_calls or not queued:
        # The tool was in front of them and named in the ask; a reply with no
        # call is the bluff shape this office has caught four times. One
        # plain re-run with the fact in front of them.
        _log(f"{agent_id}/{slot}: described in prose, no change_my_picture "
             f"(tools={tool_calls}) -- re-running once")
        nudge = ("\n\n[Your reply described the picture but did not call "
                 "change_my_picture, so nothing was queued. Call it now with "
                 f"slot '{slot}' and your description.]")
        async with httpx.AsyncClient(timeout=600) as cx:
            r2 = await cx.post("http://127.0.0.1:8420/api/chat",
                               json={"agent_id": agent_id, "message": prompt + nudge,
                                     "task": True})
        r2.raise_for_status()
        tool_calls = (r2.json() or {}).get("tool_calls") or []
        queued = _pending_scene(agent_id, slot)
    if not queued:
        _log(f"{agent_id}/{slot}: NOT queued after re-run (tools={tool_calls})")
        return {"ok": False, "agent_id": agent_id, "slot": slot, "tools": tool_calls}
    _log(f"{agent_id}/{slot}: queued -> approval {queued}")
    return {"ok": True, "agent_id": agent_id, "slot": slot, "approval_id": queued}


async def refresh_now(agent_id: str | None = None, slot: str | None = None) -> dict:
    """Manual trigger. Marks state so the rotation moves on."""
    st = _state()
    if not agent_id:
        agent_id, auto_slot = next_agent(st)
        slot = slot or auto_slot
    elif not slot:
        _, slot = next_agent({agent_id: st.get(agent_id) or {}})
    now = datetime.datetime.now().isoformat(timespec="seconds")
    st["_last_ask"] = now
    _save(st)
    res = await refresh(agent_id, slot)
    st[agent_id] = {"asked": now, "slot": slot,
                    **{k: v for k, v in res.items() if k in ("ok", "approval_id")}}
    _save(st)
    return res


def status() -> dict:
    st = _state()
    aid, slot = next_agent(st)
    last = _last_refresh(st)
    due = (last + datetime.timedelta(hours=gap_hours())) if last else datetime.datetime.now()
    return {"enabled": is_enabled(), "gap_hours": gap_hours(),
            "next_agent": aid, "next_slot": slot,
            "due": due.isoformat(timespec="minutes"), "history": st}


async def tick() -> None:
    if not is_enabled():
        return
    if ideation._active_chat_count > 0 or ideation._video_building():
        return
    try:
        import comfy_image
        if comfy_image.render_in_progress():
            return
    except Exception:
        pass
    st = _state()
    last = _last_refresh(st)
    now = datetime.datetime.now()
    if last and now - last < datetime.timedelta(hours=gap_hours()):
        return
    agent_id, slot = next_agent(st)
    if _pending_scene(agent_id, slot):
        # Barry has not clicked the last one; do not stack. Move the clock so
        # the next seat gets its turn on the next tick instead of this one
        # blocking the whole rotation.
        _log(f"{agent_id}/{slot}: still pending from last time -- skipping, "
             "rotation moves on")
        st[agent_id] = {**(st.get(agent_id) or {}),
                        "asked": now.isoformat(timespec="seconds"), "slot": slot,
                        "skipped": "pending"}
        _save(st)
        return
    st[agent_id] = {"asked": now.isoformat(timespec="seconds"), "slot": slot}
    st["_last_ask"] = now.isoformat(timespec="seconds")
    _save(st)                              # mark first so a crash cannot double-ask
    res = await refresh(agent_id, slot)
    st[agent_id].update({k: v for k, v in res.items() if k in ("ok", "approval_id")})
    _save(st)


async def run_home_refresh_loop() -> None:
    await asyncio.sleep(STARTUP_DELAY_SECONDS)
    while True:
        try:
            await tick()
        except Exception as e:  # noqa: BLE001 -- a loop must never die
            _log(f"loop error: {type(e).__name__}: {e}")
        await asyncio.sleep(CHECK_EVERY_SECONDS)
