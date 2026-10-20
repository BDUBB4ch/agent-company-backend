"""THE DAILY LEARNING REVIEW (2026-09-24, Barry: "build the learning system").

Once a day per seat, on the clock and only when that seat had REAL outcomes (outcomes.py), the office
tells the agent what happened and lets the agent decide what it learned -- in its own words, citing
the event as evidence, or judging an old lesson confirmed/contradicted (lessons.judge). Code never
writes a lesson (Barry: tell them, don't alter them). Research basis: learn from outside-checked
outcomes, itemized lessons with helpful/harmful counts, archive what fails, promote what holds 3x
(docs/reliability-research-2026-09-24.md + the learning report).

Same shape as email_cadence: /api/chat with task=True (kept out of his thread), work hours only, never
while he is chatting or a render holds the GPU, ONE seat per tick so it never stacks GPU turns.
State: data/learning_review_state.json. Log: data/learning_review.log.
Manual: `await review_now("BusinessOps")`.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import os

import httpx

import clock
import lessons
import outcomes

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(_ROOT, "data", "learning_review_state.json")
LOG = os.path.join(_ROOT, "data", "learning_review.log")
STARTUP_DELAY_SECONDS = 300
CHECK_EVERY_SECONDS = 1200
MAX_EVENTS = 12
NEVER = {"taliyah", "Taliyah"}          # the companion seat: no work outcomes, no review


def _log(msg: str) -> None:
    try:
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}\n")
    except OSError:
        pass


def _state() -> dict:
    try:
        with open(STATE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save(st: dict) -> None:
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(st, fh, indent=1)
    os.replace(tmp, STATE)


def _agent_id(office: str) -> str | None:
    import agents
    import memory
    aid = agents.OFFICE_NAME_TO_AGENT_ID.get(office)
    if aid:
        return aid
    return next((c["agent_id"] for c in memory.get_custom_agents() if c.get("office_name") == office), None)


def _first_name(office: str) -> str:
    import reflect
    import memory
    aid = _agent_id(office) or office
    if aid in reflect.HUMAN_NAMES:
        return reflect.HUMAN_NAMES[aid]
    hire = next((c for c in memory.get_custom_agents() if c.get("agent_id") == aid), None)
    return (hire or {}).get("name") or office


def build_prompt(office: str, events: list[dict]) -> str:
    lines = [
        "LEARNING REVIEW (the office, once a day). These things REALLY happened in your work since your "
        "last review -- each one is an outside check (the office's claim/number checks, a read-back, a "
        "tool error, or Barry's own approve/reject click), not anyone's opinion:",
    ]
    for e in events:
        lines.append(f"- [{e['id']}] {e['ts'][5:16].replace('T', ' ')} {e['kind']}: {e['detail']}")
    lines += [
        "",
        "Your lessons ledger is in front of you, numbered. For these events, use your own judgment:",
        "- If one teaches you something you will do differently, call remember_lesson: the lesson in your "
        "own words, why, how -- and evidence = the event id(s). One lesson can cover several events.",
        "- If one confirms or contradicts a lesson already on your ledger, call remember_lesson with "
        "about_lesson = its number and verdict = confirmed or contradicted (plus the evidence ids).",
        "- If an event teaches nothing (a one-off, not something you did), leave it.",
        "Lessons are about how you WORK. Keep them true to what the events show.",
    ]
    promo = lessons.ready_to_promote(office)
    if promo:
        lines.append("")
        for n, it in promo[:3]:
            lines.append(f"Lesson #{n} has now held up {lessons.PROMOTE_AT}+ times. If it is a real way of "
                         "working, you may keep it for good as a skill with save_note (title, content, "
                         "when_useful) -- your call.")
    lines += ["", "Finish with one short line: what you kept or judged, or 'nothing to learn today'."]
    return "\n".join(lines)


async def review_now(office: str) -> dict:
    """Run one review for one seat now (real outcomes only). Returns what happened."""
    if office in NEVER:
        return {"ok": False, "why": "companion seat -- not reviewed"}
    events = outcomes.pending(office, MAX_EVENTS)
    if not events:
        return {"ok": False, "why": "no unreviewed outcomes"}
    aid = _agent_id(office)
    if not aid:
        return {"ok": False, "why": f"no agent for office {office!r}"}
    before = len(lessons.load(office))
    prompt = build_prompt(office, events)
    async with httpx.AsyncClient(timeout=1500) as cx:
        r = await cx.post("http://127.0.0.1:8420/api/chat",
                          json={"agent_id": aid, "message": prompt, "task": True, "activity": "daily learning review"})
    reply = (r.json() or {}).get("reply", "") if r.status_code == 200 else ""
    if r.status_code != 200:
        _log(f"{office}: chat HTTP {r.status_code} -- events left unreviewed")
        return {"ok": False, "why": f"chat HTTP {r.status_code}"}
    outcomes.mark_reviewed(office, [e["id"] for e in events])
    items = lessons.load(office)
    for n, it in lessons.ready_to_promote(office):
        it["promoted"] = datetime.date.today().isoformat()      # offered once; the agent decides
    lessons._save(office, items)
    after = len(lessons.load(office))
    _log(f"{office}: reviewed {len(events)} events; lessons {before} -> {after}; reply: {reply[:160]!r}")
    return {"ok": True, "events": len(events), "lessons_before": before, "lessons_after": after,
            "reply": reply[:400]}


def prune_all() -> None:
    """Once a day: archive lessons real outcomes kept contradicting / self-only ones never confirmed."""
    if not os.path.isdir(lessons.LESSONS_DIR):
        return
    for f in os.listdir(lessons.LESSONS_DIR):
        if not f.endswith(".json"):
            continue
        office = f[:-5]
        items = lessons.load(office)
        gone = lessons.prune(items)
        if gone:
            lessons._save(office, items)
            lessons.refresh_ledger(office, _first_name(office))
            _log(f"{office}: archived {len(gone)} lesson(s): {[g[:60] for g in gone]}")


async def tick() -> None:
    if not clock.is_work_hours():
        return
    try:
        import ideation
        if ideation._active_chat_count > 0 or ideation._video_building():
            return
        import comfy_image
        if comfy_image.render_in_progress():
            return
    except Exception:                                   # noqa: BLE001
        pass
    st = _state()
    today = datetime.date.today().isoformat()
    if st.get("_pruned") != today:
        prune_all()
        st["_pruned"] = today
        _save(st)
    for office in outcomes.offices_with_pending():
        if office in NEVER or st.get(office) == today:
            continue
        st[office] = today
        _save(st)                                       # mark first: a crash can't double-run
        res = await review_now(office)
        st[f"{office}_last"] = {k: v for k, v in res.items() if k != "reply"}
        _save(st)
        return                                          # one seat per tick


async def run_learning_review_loop() -> None:
    await asyncio.sleep(STARTUP_DELAY_SECONDS)
    while True:
        try:
            await tick()
        except Exception as e:                          # noqa: BLE001 -- a loop must never die
            _log(f"loop error: {type(e).__name__}: {e}")
        await asyncio.sleep(CHECK_EVERY_SECONDS)
