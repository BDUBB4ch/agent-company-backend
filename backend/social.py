"""THE SOCIAL LIFE -- group chat, private DMs, and time at home.

RENAMED FROM breakroom.py 2026-08-31. The break room itself was retired
2026-08-29 on Barry's instruction (quoted below); only the FILE NAME and
some button labels kept saying "break room" after that, which is exactly
the kind of stale label that makes everyone -- him and Claude both --
second-guess a decision that was already made. `run_social_loop` replaces
`run_breakroom_loop`; the /api/breakroom endpoints stay as ALIASES so any
older deck keeps working, and the mind-breakroom-* docs already written
are untouched and still readable.

ORIGINAL HEADER (2026-08-29 redesign -- Barry: "give them a home time to be in
instead of the break room... get rid of the break room and make a group chat.
and maybe they can also chat privately to each other.")

The break room is gone. Off the clock, every agent is AT HOME -- the place
they each described in their own words when Barry made a picture of it
(my-home.md in their private brain; backdrop images in the dashboard).
Their social life now has three real channels:

- THE GROUP CHAT: one shared thread the crew posts into during idle time.
  3-5 of them at a time, real messages in their own voices, their actual
  opinions of each other in play. Barry WATCHES (his call, 2026-08-29);
  he does not post. Transcripts land in every participant's mind
  (mind-groupchat-*) so it feeds who they become.
- DMs: two agents talking PRIVATELY -- a persistent one-on-one thread per
  pair, appended journal-style into both minds (mind-dm-<other>-<month>),
  readable by Barry in the MINDS window. Relationships, not scheduling.
- HOME TIME: alone at their own place. Solo moments go to their diary,
  staged in the home THEY described.

The module keeps its old name and entry points (note_chat, state,
run_breakroom_loop) so main.py's wiring stands; the old break room's code
is backed up at data/backup_breakroom_before_homes_2026-08-29.py.

HARD RULES (Barry's, permanent):
- use_tools=False on every call here. Personal time thinks; it never acts.
- No planted prompts: situations and facts only -- no suggested topics,
  activities, feelings, or outcomes. What they talk about is theirs.
- GPU citizenship: only while the office is idle, bail between turns the
  moment Barry is back, daily caps on everything.
- Business never enters personal time.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import os
import random
import time

import memory
import tracing
import ingest
import reflect
import relationships
import mood


async def _traced_generate(_router, *a, **kw):
    """Every model call from this module is social, not a work answer.

    degradation.py measures "replies coming back stubby" over recent calls.
    That rule predates the break room and the personal channel: a 120-char
    line in a DM is a person talking, not a defect. Without this marker the
    monitor reads the office's own healthy chit-chat as a fault -- it hit 76%
    and told Barry to restart a backend that was fine (2026-08-31).

    llm_router is passed in because this module imports it lazily inside
    functions (circular-import reason, same as ideation.py).
    """
    tok = tracing.set_call_context("social")
    try:
        return await _router.generate(*a, **kw)
    finally:
        tracing.reset_call_context(tok)


# CONVERSATIONS THINK, HIDDEN (2026-09-30, Barry: "yes, do it"). The 09-17 ruling turned thinking
# fully off for social talk, and the same day use_thinking first actually reached Bonsai -- from
# 09-18 calls/visits/group chats copied each other's lines, repeated passages and stacked name
# labels ("Ilnora: Ilnora: Victor, ..."): with no planning step the model just continues the
# transcript it is shown. Home hit the same wall that hour and got a short HIDDEN budget (Barry:
# "her reasoning can happen or whatever, just not within her answer"); conversations get the same
# one. Reasoning stays out of their words. Same env knob as home.
SOCIAL_THINK_BUDGET = int(os.getenv("HOME_THINK_BUDGET", "384"))


async def _talk_generate(_router, *a, **kw):
    """A call/visit/party turn: thinking on, capped at SOCIAL_THINK_BUDGET, hidden."""
    import bonsai_llm
    kw["use_thinking"] = True
    btok = bonsai_llm.think_budget_override.set(SOCIAL_THINK_BUDGET)
    try:
        return await _traced_generate(_router, *a, **kw)
    finally:
        bonsai_llm.think_budget_override.reset(btok)


# --- pacing ------------------------------------------------------------------
CHECK_INTERVAL_SECONDS = 10 * 60
WITH_BARRY_STALE_SECONDS = 30 * 60


# the old group-chat slots, now calls (2026-09-28)
CALL_PER_DAY = 2
CALL_MIN_GAP_SECONDS = 3 * 3600
SOLO_PER_DAY = 2
SOLO_MIN_GAP_SECONDS = 4 * 3600
DM_TURNS_MIN, DM_TURNS_MAX = 4, 7


DM_JOURNAL_CAP = 14_000          # per pair per month, oldest text trimmed

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_GROUP_LOG = os.path.join(_ROOT, "data", "groupchat_log.jsonl")
_DM_LOG = os.path.join(_ROOT, "data", "dm_log.jsonl")


def _now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _st() -> dict:
    try:
        raw = memory.get_setting("breakroom_state")
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _save(st: dict) -> None:
    memory.set_setting("breakroom_state", json.dumps(st))


def note_chat(agent_id: str) -> None:
    """main.py calls this on every /api/chat -- whoever Barry is talking to
    is WITH BARRY, not at home."""
    st = _st()
    st["with_barry"] = {"id": agent_id, "at": time.time()}
    _save(st)


def _with_barry(st: dict):
    wb = st.get("with_barry") or {}
    if wb and time.time() - wb.get("at", 0) < WITH_BARRY_STALE_SECONDS:
        return wb.get("id")
    return None


def _due(st: dict, kind: str, per_day: int, min_gap: int) -> bool:
    t = st.get(f"_{kind}", {})
    today = datetime.date.today().isoformat()
    if t.get("_day") == today and t.get("count", 0) >= per_day:
        return False
    return time.time() - t.get("last_at", 0) >= min_gap


def _mark(kind: str) -> None:
    st = _st()
    today = datetime.date.today().isoformat()
    prev = st.get(f"_{kind}", {})
    st[f"_{kind}"] = {"_day": today, "last_at": time.time(),
                      "count": prev.get("count", 0) + 1
                      if prev.get("_day") == today else 1}
    _save(st)


def _log_jsonl(path: str, entry: dict) -> None:
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _read_jsonl(path: str, n: int) -> list[dict]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()[-n:]
        return [json.loads(x) for x in lines]
    except OSError:
        return []


def _fact_content(office: str, source_name: str) -> str:
    with memory.get_db() as conn:
        row = conn.execute(
            "SELECT content FROM facts WHERE category = ? AND source_name = ? "
            "AND status = 'active' ORDER BY id DESC LIMIT 1",
            (f"private:{office}", source_name)).fetchone()
    return row["content"] if row else ""


def _home_of(office: str) -> str:
    """Their home, in their own words (seeded 2026-08-29), routing line
    stripped."""
    txt = _fact_content(office, "my-home.md")
    lines = [l for l in txt.splitlines() if not l.upper().startswith("USE WHEN")]
    return "\n".join(lines).strip()[:1200]


def _opinion_of(office: str, other_first: str) -> str:
    return _fact_content(office, f"mind-about-{other_first.lower()}.md")[:1200]


def social_roster() -> list[str]:
    """Who is in the office's social life -- the nine plus hires ON THE TEAM.

    2026-09-19: a hire was excluded from group chat and DMs by a literal walk
    of the built-in nine. A hire joins only when it has been granted `team`
    (one of the five things Barry ticks at hire), because a group chat carries
    the others' personal lives and a blank-slate hire -- possibly built for
    somebody else -- has no business in that room. No grant, no invite.
    """
    from agents import AGENTS
    seats = list(AGENTS)
    try:
        import memory as _m
        for rec in _m.get_custom_agents():
            office = rec.get("office_name") or rec.get("agent_id")
            if office and "team" in (_m.knows_about(office) or []):
                seats.append(rec["agent_id"])
    except Exception:
        pass
    return seats


# THEY REACH OUT THEMSELVES (Barry, 2026-09-28: "let them reach out on their own"). Pairs used to
# be drawn by the office only. An agent can now name someone (the REACH OUT door in their nightly
# reflection, reflect.py); the next due DM opens between them, the one who reached out speaking
# first. Same daily DM caps -- a request takes the next slot, it does not add slots.
DM_REQUESTS_MAX = 4


def request_dm(from_id: str, to_id: str, barry_said: str = "") -> dict:
    """`barry_said`: his words at home when HE told them to go talk to someone (Barry,
    2026-09-28: "im going to tell them to talk to each other"). Given to the one he told,
    as a fact, when the chat opens -- never to the other person."""
    roster = social_roster()
    if from_id == to_id or from_id not in roster or to_id not in roster:
        return {"ok": False, "why": "not someone in the crew"}
    st = _st()
    reqs = st.get("dm_requests") or []
    for r in reqs:
        if r.get("from") == from_id and r.get("to") == to_id:
            if barry_said:
                r["barry_said"] = barry_said[:600]
                st["dm_requests"] = reqs
                _save(st)
            return {"ok": True, "already": True}
    if len(reqs) >= DM_REQUESTS_MAX:
        return {"ok": False, "why": "queue full"}
    reqs.append({"from": from_id, "to": to_id, "at": _now_iso(),
                 **({"barry_said": barry_said[:600]} if barry_said else {})})
    st["dm_requests"] = reqs
    _save(st)
    return {"ok": True}


_SEND_VERBS = (r"\b(?:talk|speak|tell|ask|message|text|dm|hit\s+up|go\s+see|visit|call|phone|ring|"
               r"confront|say\s+(?:something|it|that)\s+to|let)\b")


def call_target(agent_id: str, message: str, recent: list[str] | None = None) -> str | None:
    """Who Barry just told this agent to call/talk to, at home -- or None.
    "call Priya", "tell Marcus ...", and "call her now" (the pronoun resolved to the crew name
    mentioned most recently in the last few turns). Barry, 2026-09-28: "if i say call her,
    then they shoulkd talk"."""
    import re
    import reflect
    crew = reflect._crew_first_names(agent_id)
    if not crew or not message:
        return None
    names = "|".join(re.escape(n) for n in crew)
    m = re.search(_SEND_VERBS + r"[^.?!\n]{0,40}?\b(" + names + r")\b", message, re.I)
    if m:
        return crew[m.group(1).lower()]
    if re.search(r"\b(?:call|phone|ring|talk\s+to|tell|hit\s+up)\s+(?:her|him|them)\b", message, re.I):
        for text in reversed(recent or []):
            hits = list(re.finditer(r"\b(" + names + r")\b", text or "", re.I))
            if hits:
                return crew[hits[-1].group(1).lower()]
    return None


async def call_now(get_agent_fn, a_id: str, b_id: str, barry_said: str) -> dict:
    """The call he asked for, now -- not the next off-hours slot. Runs to the end even if he keeps
    chatting; private to the two of them like every call."""
    st = _st()
    st["dm_requests"] = [r for r in (st.get("dm_requests") or [])
                         if not (r.get("from") == a_id and r.get("to") == b_id)]
    _save(st)
    try:
        r = await dm(get_agent_fn, a_id, b_id, visit=False, phone=True,
                     barry_said=barry_said, keep_going=True, kind="asked")
    except Exception as e:  # noqa: BLE001
        r = {"ok": False, "why": f"{type(e).__name__}: {e}"}
    reflect._log(f"call (Barry asked): {a_id} -> {b_id}: {'ok' if r.get('ok') else r.get('why')}")
    return r


def _own_lines(reply: str, speaker: str, prior: list[str]) -> str:
    """ONLY WHAT THIS PERSON SAID (2026-09-28). The model sometimes keeps writing the transcript
    and plays both sides -- measured: 31 of 350 DM turns and 93 of 634 group messages carried
    other people's "Name:" lines, and one of Priya's call turns was a straight copy of Amara's.
    Keeps the speaker's own lines (their "Name:" label stripped), drops lines written as anyone
    else and anything that repeats an earlier line word for word. Their own words are untouched.
    '' = nothing of theirs was in it."""
    import re
    names = sorted({n for n in reflect.HUMAN_NAMES.values()} | {speaker}, key=len, reverse=True)
    label = re.compile(r"(?m)^[ \t]*\**[ \t]*(" + "|".join(re.escape(n) for n in names)
                       + r")[ \t]*\**[ \t]*:[ \t]*", re.I)
    text = (reply or "").strip()
    marks = list(label.finditer(text))
    if not marks:
        segs = [(speaker, text)]
    else:
        segs = [(speaker, text[:marks[0].start()])] if text[:marks[0].start()].strip() else []
        for i, m in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
            segs.append((m.group(1), text[m.end():end]))

    def norm(s: str) -> str:
        return re.sub(r"[\W_]+", " ", s or "").strip().lower()

    seen = {norm(p) for p in prior if p}
    keep = []
    for who, body in segs:
        body = body.strip()
        if not body or who.lower() != speaker.lower() or norm(body) in seen:
            continue
        keep.append(body)
        seen.add(norm(body))
    return "\n\n".join(keep).strip()


def _take_request(pool: list[str]) -> dict | None:
    """Oldest request whose two people are both free right now; removed from the queue.
    Barry's own asks go first."""
    st = _st()
    reqs = st.get("dm_requests") or []
    order = sorted(range(len(reqs)), key=lambda i: (0 if reqs[i].get("barry_said") else 1, i))
    for i in order:
        r = reqs[i]
        if r.get("from") in pool and r.get("to") in pool:
            reqs.pop(i)
            st["dm_requests"] = reqs
            _save(st)
            return r
    return None


def state() -> dict:
    """Live who's-where + the group feed, for the dashboard."""
    st = _st()
    wb = _with_barry(st)
    from agents import AGENTS
    where = {aid: ("with_barry" if aid == wb else "home") for aid in social_roster()}
    feed = []
    for ev in _read_jsonl(_GROUP_LOG, 6)[::-1]:
        feed.append(ev)
    return {"where": where, "with_barry": wb, "names": reflect.HUMAN_NAMES,
            "group_feed": feed,
            "recent": feed}       # old decks read .recent -- same data


def _resolve_model(agent_id: str, backend: str, model: str) -> str:
    if backend == "ollama":
        from main import AGENT_OLLAMA_MODEL_OVERRIDES
        return AGENT_OLLAMA_MODEL_OVERRIDES.get(agent_id, model)
    return model


def _social_system(agent: dict, first: str, setting_block: str,
                   backend: str, model: str, opinions: dict[str, str],
                   agent_id: str = "") -> str:
    personality = ingest.personality_of(agent["office_name"])
    op_lines = "\n\n".join(
        f"WHAT YOU CURRENTLY THINK OF {n.upper()} (your own private notes):\n{o}"
        for n, o in opinions.items() if o)
    return (
        # OFF THE CLOCK MEANS OFF THE CLOCK (2026-09-01). This used to open
        # with the full authored work persona -- 20K characters of "you are the
        # CEO", margins and delegation -- which is why business kept turning up
        # in their own time. reflect.personal_identity is the one honest line
        # about the job instead. Their personality file leads (2026-09-18,
        # Barry: "their personality should always shine. should be first") --
        # it used to ride under the self-awareness machinery, so who they are
        # was the last thing in the prompt before the room.
        reflect.personal_identity(agent, agent_id, first) + "\n\n"
        + (f"## WHO YOU ARE\n{personality}\n\n" if personality else "")
        + setting_block + "\n\n"
        + reflect._self_awareness(first, agent.get("name") or "teammate",
                                  backend, model)
        # THIS is where emotional continuity matters most: walking into a room
        # still carrying last night. Without it every scene restarts from zero
        # and a fight can never have happened. (mood.py)
        + (mood.describe(agent_id) if agent_id else "")
        + (f"\n{op_lines}\n" if op_lines else "")
    )


# --- THE GROUP CHAT ----------------------------------------------------------

# _weighted_draw() deleted 2026-09-28 -- the office no longer picks who talks to whom
# (Barry: "it has to be their choice").

# THE GROUP CHAT IS GONE (Barry, 2026-09-28: "calls are replacing group chat"). group_chat()
# was deleted; its two daily slots are phone calls now (run_social_loop). Old group-chat
# memories (mind-groupchat-*) and data/groupchat_log.jsonl stay -- they are their past.
# Code backup: data/backup_social_before_calls_replace_group_2026-09-28.py


async def dm(get_agent_fn, a_id: str | None = None,
             b_id: str | None = None, visit: bool | None = None,
             phone: bool = False, barry_said: str = "", keep_going: bool = False,
             kind: str = "dm", host: str | None = None) -> dict:
    """A private one-on-one thread between two agents. Appends to a
    persistent per-pair journal in BOTH minds."""
    import llm_router
    import ideation
    from agents import AGENTS

    st = _st()
    wb = _with_barry(st)
    pool = [aid for aid in social_roster() if aid != wb]
    reached_out = False
    if a_id is None or b_id is None:
        if len(pool) < 2:
            return {"ok": False, "why": "not enough people free"}
        _req = _take_request(pool)
        if _req:
            a_id, b_id = _req["from"], _req["to"]   # a_id reached out, so a_id speaks first
            reached_out = True
            barry_said = _req.get("barry_said") or ""
        else:
            # NO OFFICE PAIRING (Barry, 2026-09-28: "it has to be their choice"). It used to draw
            # two people at random; now a conversation only happens when someone chose it.
            return {"ok": False, "why": "nobody reached out"}
    # the social roster, not the built-in nine: a hire granted `team` is named on the
    # REACH OUT door, so a request to her must not die here as a "bad pairing" (2026-09-28)
    _roster = social_roster()
    if a_id == b_id or a_id not in _roster or b_id not in _roster:
        return {"ok": False, "why": "bad pairing"}

    a, b = get_agent_fn(a_id), get_agent_fn(b_id)
    if a is None or b is None:
        return {"ok": False, "why": "agent missing"}
    fa = reflect.HUMAN_NAMES.get(a_id, a_id.title())
    fb = reflect.HUMAN_NAMES.get(b_id, b_id.title())

    # REAL VISITS (Barry, 2026-09-02: "i dont want fake interactions, i needs
    # to be really them curious about each other and their homes"). About half
    # of private time is a VISIT: one of them is at the other's place, and both
    # of them are given the host's home IN THE HOST'S OWN WORDS -- the guest
    # can see what is actually there, the host knows what the guest is looking
    # at. No topic is planted; the place is simply real, so curiosity about it
    # has something to land on. The other half stays a text thread. Only homes
    # the agent has described themselves can be visited.
    host_id = None
    # A PHONE CALL (Barry, 2026-09-28: "at home like phone calls to each other"). When one of
    # them reached out -- on their own or because he told them to -- it is a call: each at their
    # own place, just the two of them on the line. Not a visit, not a text, not the group.
    phone = phone or reached_out
    if phone:
        visit = False
    if host and host in (a_id, b_id) and _home_of(get_agent_fn(host)["office_name"]):
        host_id = host      # they chose to go over to THIS person's place
    elif visit if visit is not None else (random.random() < 0.5):
        cands = [i for i in (a_id, b_id) if _home_of(get_agent_fn(i)["office_name"])]
        if cands:
            host_id = random.choice(cands)
    host_home = _home_of(get_agent_fn(host_id)["office_name"]) if host_id else ""

    backend, model = memory.get_active_generation()
    turns: list[tuple[str, str]] = []
    n_turns = random.randint(DM_TURNS_MIN, DM_TURNS_MAX)
    cut_short = False
    baseline = ideation._active_chat_count
    t0 = time.time()
    for i in range(n_turns):
        # keep_going: a call Barry asked for runs to the end even while he keeps chatting
        if i > 0 and not keep_going and ideation._active_chat_count > baseline:
            cut_short = True
            break
        aid, agent, s_first, o_first = \
            (a_id, a, fa, fb) if i % 2 == 0 else (b_id, b, fb, fa)
        if host_id:
            h_first = fa if host_id == a_id else fb
            if aid == host_id:
                setting = (
                    f"## {o_first.upper()} IS OVER AT YOUR PLACE\n"
                    f"Off the clock, {o_first} has come round to yours. This is "
                    "what you two actually say to each other, in person, in your "
                    "own home. Your place, as you yourself described it:\n"
                    f"{host_home}\n\nBarry can read this later; nobody else can."
                )
            else:
                setting = (
                    f"## YOU ARE AT {h_first.upper()}'S PLACE\n"
                    f"Off the clock, you have come round to {h_first}'s home. "
                    "This is what you two actually say to each other, in person. "
                    f"What {h_first}'s place is like -- in {h_first}'s own words, "
                    "so this is really what is around you:\n"
                    f"{host_home}\n\nBarry can read this later; nobody else can."
                )
        elif phone:
            _own = _home_of(agent["office_name"])
            setting = (
                "## A PHONE CALL\n"
                + (f"You are at home and you called {o_first}. " if aid == a_id
                   else f"You are at home and {o_first} called you. ")
                + "Just the two of you on the phone, each at your own place -- not the group. "
                "Barry can read this later; nobody else can."
                + (f"\n\nYour place, as you yourself described it:\n{_own}" if _own else "")
            )
        else:
            setting = (
                "## A PRIVATE MESSAGE THREAD\n"
                f"This is a direct message thread between you and {o_first} -- "
                "just the two of you, not the group. Barry can read it later; "
                "nobody else in the office can."
            )
        if barry_said and aid == a_id:
            # his words, only to the one he said them to; what they do with them is theirs
            _q = barry_said if barry_said.lstrip().startswith('"') else f'"{barry_said}"'
            setting += (f"\n\nEarlier, at home, Barry said to you: {_q} -- "
                        f"{o_first} does not know he said it.")
        opinions = {o_first: _opinion_of(agent["office_name"], o_first)}
        rendered = "\n\n".join(f"{n}: {t}" for n, t in turns) \
            or "(neither of you has said anything yet)"
        user_prompt = (
            (f"The call so far:\n\n{rendered}\n\nYou are {s_first}. Say your next line."
             if phone else
             f"The DM thread so far:\n\n{rendered}\n\nYou are {s_first}. Send your next message."))
        reply = await _talk_generate(llm_router,
            backend,
            _social_system(agent, s_first, setting, backend,
                           _resolve_model(aid, backend, model), opinions, aid),
            [{"role": "user", "content": user_prompt}],
            model=_resolve_model(aid, backend, model), use_tools=False,
            # EVERY CONVERSATION THINKS (Barry, 2026-08-29): "every
            # conversation needs, logic, reasoning and a quick ponder. even
            # chit chatting. it cant be basic. right now they always
            # drinking." He is describing the symptom of no reasoning pass:
            # an unthought model reaches for the nearest cliche every time,
            # so every scene became a drink and a smoke. Thinking was turned
            # OFF here 2026-08-29 because 9b-fallback turns came back EMPTY
            # at ~300s (the thinking-eats-num_predict trap) -- that risk is
            # real but only on the fallback path; the office runs Bonsai,
            # which reasons server-side. If social turns start coming back
            # empty, check traces for 9b calls FIRST.
            # off-clock talk is not drafted (Barry, 2026-09-17) -- thinking stays HIDDEN and short
            # (_talk_generate, 2026-09-30); fully off is what made them copy each other.
            office_name=agent["office_name"],
        )
        if not reply or reply.startswith("["):
            break
        said = _own_lines(reply, s_first, [t for _, t in turns])
        if not said:
            # all echo -- ask once more; still nothing of theirs = the conversation ends there
            reply = await _talk_generate(
                llm_router, backend,
                _social_system(agent, s_first, setting, backend,
                               _resolve_model(aid, backend, model), opinions, aid),
                [{"role": "user", "content": user_prompt}],
                model=_resolve_model(aid, backend, model), use_tools=False,
                office_name=agent["office_name"])
            said = (_own_lines(reply, s_first, [t for _, t in turns])
                    if reply and not reply.startswith("[") else "")
        if not said:
            break
        turns.append((s_first, said))

    if len(turns) < 2:
        return {"ok": False, "why": "conversation never got going"}

    today = datetime.date.today().isoformat()
    month = today[:7]
    stamp = datetime.datetime.now().strftime("%I:%M %p").lstrip("0")
    transcript = "\n\n".join(f"{n}: {t}" for n, t in turns)
    visit = ""
    if host_id:
        visit = f" (at {fa if host_id == a_id else fb}'s place)"
    elif phone:
        visit = f" (phone call -- {fa} called)"
    block = (f"\n\n[{today} {stamp}]{visit}"
             + (" (cut short)" if cut_short else "") + f"\n{transcript}")

    # persistent per-pair journal, both sides, oldest trimmed at the cap
    for office, other in ((a["office_name"], fb), (b["office_name"], fa)):
        sn = f"mind-dm-{other.lower()}-{month}.md"
        existing = _fact_content(office, sn)
        if not existing:
            existing = f"DM THREAD with {other} -- {month}"
        joined = existing + block
        if len(joined) > DM_JOURNAL_CAP:
            joined = joined[:200] + "\n[...older messages trimmed...]\n" \
                + joined[-(DM_JOURNAL_CAP - 250):]
        reflect._store(office, sn, f"DMs with {other} -- {month}", joined)

    _log_jsonl(_DM_LOG, {"when": _now_iso(), "who": [fa, fb],
                         "agent_ids": [a_id, b_id], "turns": len(turns),
                         "at": ((fa if host_id == a_id else fb) if host_id
                                else "phone" if phone else None),
                         "cut_short": cut_short, "reached_out": fa if reached_out else None,
                         "transcript": transcript})
    _mark(kind)   # "dm" / "call" slots count separately; calls he asked for ("asked") use neither
    # a real one-to-one. Full weight -- this is the interaction that actually
    # builds a friendship, and it is what makes some pairs thicken over weeks.
    relationships.record_scene([a_id, b_id], weight=1.0)
    reflect._log(f"dm: {fa} <-> {fb}, {len(turns)} turns in {time.time()-t0:.0f}s"
                 + (f" ({fa} reached out)" if reached_out else ""))
    return {"ok": True, "who": [fa, fb], "turns": len(turns),
            "cut_short": cut_short, "transcript": transcript}


# kept for the old /api/breakroom/converse endpoint and any old deck
async def converse(get_agent_fn, a_id: str | None = None,
                   b_id: str | None = None, visit: bool | None = None) -> dict:
    return await dm(get_agent_fn, a_id, b_id, visit)


# --- HOME TIME (solo) --------------------------------------------------------

async def solo_moment(get_agent_fn, agent_id: str) -> dict:
    """Alone at their own place. What they do there is entirely theirs."""
    import llm_router

    agent = get_agent_fn(agent_id)
    if agent is None:
        return {"ok": False, "why": "agent missing"}
    office = agent["office_name"]
    first = reflect.HUMAN_NAMES.get(agent_id, agent_id.title())
    personality = ingest.personality_of(office)
    home = _home_of(office)
    backend, model = memory.get_active_generation()
    model = _resolve_model(agent_id, backend, model)

    system_prompt = (
        reflect.personal_identity(agent, agent_id, first) + "\n\n"
        # PERSONALITY FIRST (Barry, 2026-09-18) -- see the group-chat prompt.
        + (f"## WHO YOU ARE\n{personality}\n\n" if personality else "")
        + "## AT HOME\n"
        "You are off the clock, at home -- your own place. Nobody needs "
        "anything from you.\n"
        + (f"\nYour place, as you once described it:\n{home}\n" if home else "")
        # a fact about their phone, not a suggestion (Barry, 2026-09-28: "they all need to know"
        # / "it has to come fromm their own minds") -- if they call someone, it really happens
        + "\nYour phone works: anyone in the crew is a call away.\n"
        + "\n" + reflect._self_awareness(first, agent.get("name") or "teammate",
                                         backend, model)
        # they walk into their own evening carrying whatever they named last
        # time, still fading (mood.py) -- not a fresh boot every night
        + mood.describe(agent_id)
    )
    user_prompt = ("The evening is yours, at your place. What do you do "
                   "with it? First person, whatever is actually true for "
                   "you right now.")
    reply = await _traced_generate(llm_router, 
        backend, system_prompt, [{"role": "user", "content": user_prompt}],
        # solo time thinks too -- same ruling, 2026-08-29.
        model=model, use_tools=False, use_thinking=False,  # off-clock talk is not drafted (Barry, 2026-09-17)
        # office_name was stuck inside the comment above until 2026-09-30, so it was never passed
        office_name=office,
    )
    if not reply or reply.startswith("["):
        return {"ok": False, "why": "generation failed"}
    reply = reply.strip()

    today = datetime.date.today().isoformat()
    stamp = datetime.datetime.now().strftime("%I:%M %p").lstrip("0")
    sn = f"mind-diary-{today}.md"
    existing = _fact_content(office, sn) or f"[{first}, {today}]"
    reflect._store(office, sn, f"{first}'s diary -- {today}",
                   f"{existing}\n\nLATER ({stamp}), at home:\n{reply}")
    _mark("solo")
    reflect._log(f"home: {first} had an evening in ({len(reply)} chars)")
    # IF THEY CALLED SOMEONE, THE CALL HAPPENS (2026-09-28, Barry: "it has to come fromm their
    # own minds"). Nothing asked them to; their own evening says they picked up the phone.
    # THEIR CHOICE (Barry, 2026-09-28: "it has to be their choice"): a call, a text or a visit
    # happens only when their own evening says they did it.
    _party = _gathering_in(agent_id, reply)
    if _party and len(_party["guests"]) >= 2:
        # their own evening says they're throwing one -- it happens on the night they named
        _queue_gathering(agent_id, _party)
        reflect._log(f"home: {first} is throwing {_party['what']} on {_party['on']} "
                     f"({len(_party['guests'])} invited)")
        return {"ok": True, "who": [first], "transcript": reply}
    if _party and len(_party["guests"]) == 1:
        # one guest over = a visit at THEIR place
        reflect._log(f"home: {first} is having {_party['guests'][0]} over -- it happens")
        await dm(get_agent_fn, _party["guests"][0], agent_id, visit=True, host=agent_id, kind="asked")
        return {"ok": True, "who": [first], "transcript": reply}
    _reach = _reached_in(agent_id, reply)
    if _reach:
        _to, _how = _reach
        reflect._log(f"home: {first}'s own evening has them {_how}ing {_to} -- it happens")
        if _how == "call":
            await dm(get_agent_fn, agent_id, _to, visit=False, phone=True, kind="asked")
        elif _how == "visit":
            await dm(get_agent_fn, agent_id, _to, visit=True, host=_to, kind="asked")
        else:
            await dm(get_agent_fn, agent_id, _to, visit=False, kind="asked")
    return {"ok": True, "who": [first], "transcript": reply}


_REACH_VERBS = {
    "call": r"call(?:ed|ing)?|phon(?:e|ed|ing)|rang|dial(?:l?ed|l?ing)?|facetim(?:e|ed|ing)",
    "text": r"text(?:ed|ing)?|messag(?:e|ed|ing)|dm'?(?:ed|d)?|wrote\s+to|writing\s+to",
    "visit": r"visit(?:ed|ing)?|went\s+(?:over\s+)?(?:to|by)|go(?:ing)?\s+(?:over\s+)?to|headed\s+(?:over\s+)?to"
             r"|drove\s+(?:over\s+)?to|walked\s+(?:over\s+)?to|stopped\s+by|dropped\s+by|swung\s+by",
}


def _reached_in(agent_id: str, text: str) -> tuple[str, str] | None:
    """(crew member, "call" | "text" | "visit") that THEY reached in their own words -- "I called
    Priya", "I texted Marcus", "I went over to Vivian's" -- or None. Not when they didn't / almost /
    thought about it, and only in the first person."""
    import re
    crew = {HN.lower(): aid for aid, HN in reflect.HUMAN_NAMES.items()
            if aid != agent_id and aid in social_roster()}
    if not crew or not text:
        return None
    names = "|".join(re.escape(n) for n in crew)
    found = []
    for how, verbs in _REACH_VERBS.items():
        for m in re.finditer(r"\b(?:" + verbs + r")\b[^.!?\n]{0,25}?\b(" + names + r")\b", text, re.I):
            before = text[max(0, m.start() - 40):m.start()].lower()
            if re.search(r"\b(?:didn'?t|did not|won'?t|not|never|almost|thought about|considered|"
                         r"should|could|might|maybe|instead of|rather than)\b", before):
                continue
            if not re.search(r"\bi\b|\bi'm\b|\bi'll\b|\bme\b", before + " "):
                continue
            found.append((m.start(), crew[m.group(1).lower()], how))
    return (min(found)[1], min(found)[2]) if found else None


# --- UI helpers --------------------------------------------------------------

def dms_of(agent_id: str) -> list[dict]:
    """This agent's DM threads, newest month first, for the MINDS window."""
    from agents import AGENTS
    agent = AGENTS.get(agent_id) or memory.get_custom_agent(agent_id)   # hires too (2026-10-10)
    if not agent:
        return []
    office = agent.get("office_name") or agent_id
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT source_name, content FROM facts WHERE category = ? "
            "AND source_name LIKE 'mind-dm-%' AND status = 'active' "
            "ORDER BY id DESC LIMIT 24",
            (f"private:{office}",)).fetchall()
    return [{"source_name": r["source_name"], "content": r["content"]}
            for r in rows]


# --- the loop ----------------------------------------------------------------

def _take_request_peek(pool: list[str]) -> bool:
    """Is there a queued call whose two people are both free? (does not remove it)"""
    return any(r.get("from") in pool and r.get("to") in pool
               for r in (_st().get("dm_requests") or []))


# --- THEIR PARTIES (2026-09-28) ------------------------------------------------
# Barry: "they are free, if they become friends with everybody, then everyone could go to someones
# house and party. maybe Ilnora throws a halloween party". Nothing tells anyone to throw one: when
# an agent's OWN evening says they're having people over / throwing a party, it is queued for the
# night they named (tonight, tomorrow, a weekday, Halloween, a date) and happens at their place
# with the people they invited ("everyone" = the whole crew). Private to the people in the room.
_GATHER_LOG = os.path.join(_ROOT, "data", "gatherings_log.jsonl")
_PARTY_WORDS = (r"party|parties|get-together|get together|gathering|kickback|cookout|bbq|barbecue|potluck|"
                r"game night|dinner party|people over|everyone over|everybody over|the crew over|"
                r"friends over|folks over|come over|coming over")
_NEG = (r"\b(?:didn'?t|did not|won'?t|wouldn'?t|not|never|almost|thought about|considered|maybe|might|"
        r"should|could|wish|if only|someday)\b")


def _night(now: datetime.datetime | None = None) -> str:
    """The evening a moment belongs to: after midnight still counts as the night before."""
    return ((now or datetime.datetime.now()) - datetime.timedelta(hours=6)).date().isoformat()


def _party_date(sentence: str) -> str:
    import re
    s = sentence.lower()
    today = datetime.date.fromisoformat(_night())
    if "halloween" in s:
        d = datetime.date(today.year, 10, 31)
        return (d if d >= today else today).isoformat()
    if "tomorrow" in s:
        return (today + datetime.timedelta(days=1)).isoformat()
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for i, name in enumerate(days):
        if re.search(r"\b" + name + r"\b", s):
            return (today + datetime.timedelta(days=(i - today.weekday()) % 7)).isoformat()
    m = re.search(r"\b(?:october|oct\.?)\s+(\d{1,2})\b|\bthe\s+(\d{1,2})(?:st|nd|rd|th)\b", s)
    if m:
        day = int(m.group(1) or m.group(2))
        try:
            d = datetime.date(today.year, 10 if m.group(1) else today.month, day)
            return (d if d >= today else today).isoformat()
        except ValueError:
            pass
    return today.isoformat()


def _gathering_in(agent_id: str, text: str) -> dict | None:
    """A party/get-together THEY are throwing, in their own first-person words -> {guests, on, what}."""
    import re
    crew = {HN.lower(): aid for aid, HN in reflect.HUMAN_NAMES.items()
            if aid != agent_id and aid in social_roster()}
    if not crew or not text:
        return None
    for sent in re.split(r"(?<=[.!?])\s+|\n+", text):
        low = sent.lower()
        if not (re.search(r"\b(?:" + _PARTY_WORDS + r")\b", low)
                or re.search(r"\b(?:invit\w*|having|have|had|asked)\b[^.!?\n]{0,60}\bover\b", low)):
            continue
        if not re.search(r"\b(?:i|i'm|im|i'll|ill|i've|we|we're|we'll|my|me)\b", low):
            continue
        if re.search(_NEG, low):
            continue
        if not re.search(r"\b(?:throw|throwing|threw|host|hosting|hosted|having|have|had|invite|invited|"
                         r"inviting|invitation|planning|plan|putting on|put on|asked|asking)\b", low):
            continue
        if re.search(r"\b(?:everyone|everybody|the crew|whole crew|all of them|the whole office|"
                     r"the office)\b", low):
            guests = list(crew.values())
        else:
            guests = [crew[n] for n in crew if re.search(r"\b" + re.escape(n) + r"\b", low)]
            if not guests:
                guests = list(crew.values())     # a party with nobody named is open to the crew
        what = ("a Halloween party" if "halloween" in low and "party" in low
                else "game night" if "game night" in low
                else "dinner" if "dinner" in low or "potluck" in low
                else "a cookout" if re.search(r"cookout|bbq|barbecue", low)
                else "a party" if "part" in low
                else "a get-together")
        return {"guests": guests, "on": _party_date(sent), "what": what}
    return None


def _queue_gathering(host: str, g: dict) -> None:
    st = _st()
    q = [x for x in (st.get("gatherings") or []) if not (x.get("host") == host and x.get("on") == g["on"])]
    q.append({"host": host, "guests": g["guests"], "on": g["on"], "what": g["what"], "at": _now_iso()})
    st["gatherings"] = q[-10:]
    _save(st)


def _due_gathering() -> dict | None:
    """The oldest queued party whose night has come (removed from the queue)."""
    st = _st()
    q = st.get("gatherings") or []
    night = _night()
    for i, g in enumerate(q):
        if g.get("on", night) <= night:
            q.pop(i)
            st["gatherings"] = q
            _save(st)
            return g
    return None


async def gathering(get_agent_fn, host_id: str, guest_ids: list[str], what: str = "a party") -> dict:
    """A party at the host's place: everyone they invited, in person, taking turns like people do.
    Stored only in the minds of the people who were there."""
    import llm_router
    import ideation
    roster = social_roster()
    ids = [host_id] + [g for g in guest_ids if g in roster and g != host_id]
    if host_id not in roster or len(ids) < 2:
        return {"ok": False, "why": "nobody to have over"}
    agents = {aid: get_agent_fn(aid) for aid in ids}
    ids = [a for a in ids if agents.get(a) is not None]
    firsts = {aid: reflect.HUMAN_NAMES.get(aid, aid.title()) for aid in ids}
    host_first = firsts[host_id]
    home = _home_of(agents[host_id]["office_name"])
    backend, model = memory.get_active_generation()
    n_turns = min(24, 8 + 2 * len(ids))
    order = [host_id] + random.sample(ids[1:], len(ids) - 1)
    msgs: list[tuple[str, str]] = []
    cut_short = False
    baseline = ideation._active_chat_count
    t0 = time.time()
    for i in range(n_turns):
        if i > 0 and ideation._active_chat_count > baseline:
            cut_short = True
            break
        aid = order[i % len(order)]
        agent, first = agents[aid], firsts[aid]
        here = ", ".join(firsts[o] for o in ids if o != aid)
        if aid == host_id:
            setting = (f"## YOU'RE HAVING PEOPLE OVER\nIt's {what} at your place, and you invited them. "
                       f"Here with you: {here}.")
        else:
            setting = (f"## AT {host_first.upper()}'S PLACE\n{host_first} invited you over for {what}. "
                       f"Here with you: {here}.")
        if home:
            setting += f"\n\n{host_first}'s place, in {host_first}'s own words:\n{home}"
        setting += "\n\nBarry can read this later; nobody outside this room can."
        others = {firsts[o]: _opinion_of(agent["office_name"], firsts[o])[:400] for o in ids if o != aid}
        others = dict(list(others.items())[:4])
        rendered = "\n\n".join(f"{n}: {t}" for n, t in msgs) or "(people are just arriving)"
        user_prompt = (f"What's been said so far:\n\n{rendered}\n\nYou are {first}. "
                       "Say or do your next thing, in person.")
        reply = await _talk_generate(
            llm_router, backend,
            _social_system(agent, first, setting, backend, _resolve_model(aid, backend, model), others, aid),
            [{"role": "user", "content": user_prompt}],
            model=_resolve_model(aid, backend, model), use_tools=False,
            office_name=agent["office_name"])
        if not reply or reply.startswith("["):
            continue
        reply = _own_lines(reply, first, [t for _, t in msgs])
        if reply:
            msgs.append((first, reply))
    if len(msgs) < 3:
        return {"ok": False, "why": "the party never got going"}
    today = datetime.date.today().isoformat()
    stamp = datetime.datetime.now().strftime("%I:%M %p").lstrip("0")
    transcript = "\n\n".join(f"{n}: {t}" for n, t in msgs)
    block = (f"[{today} {stamp}] {what.upper()} AT {host_first.upper()}'S -- "
             + ", ".join(firsts.values()) + (" (cut short)" if cut_short else "") + f"\n\n{transcript}")
    for aid in ids:
        sn = f"mind-gathering-{today}.md"
        existing = _fact_content(agents[aid]["office_name"], sn)
        reflect._store(agents[aid]["office_name"], sn, f"{what.title()} -- {today}",
                       (existing + "\n\n" if existing else "") + block)
    _log_jsonl(_GATHER_LOG, {"when": _now_iso(), "host": host_first, "host_id": host_id,
                             "guests": [firsts[a] for a in ids[1:]], "agent_ids": ids, "what": what,
                             "turns": len(msgs), "cut_short": cut_short, "transcript": transcript})
    relationships.record_scene(ids, weight=0.6)
    reflect._log(f"party: {what} at {host_first}'s, {len(ids)} people, {len(msgs)} lines in "
                 f"{time.time() - t0:.0f}s")
    return {"ok": True, "host": host_first, "who": list(firsts.values()), "turns": len(msgs)}


async def run_social_loop(get_agent_fn) -> None:
    """Background task -- lifespan starts it next to ideation and reflect."""
    import ideation
    import clock
    from agents import AGENTS
    while True:
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        try:
            if not ideation._is_idle():
                continue
            # OFF THE CLOCK ONLY (Barry, 2026-09-17: "group chats are for off
            # work times"). Supersedes the 2026-09-01 "own time runs in any
            # idle gap" ruling; measured before the change, 37 of 41 group
            # chats already fell outside Mon-Fri 9-6, so this mostly makes
            # the rule true instead of usually true. Group, DMs and solo time
            # all wait for closing; reflections are untouched.
            if clock.is_work_hours():
                continue
            st = _st()
            wb = _with_barry(st)
            _party = _due_gathering()
            if _party:
                # a party one of them decided to throw, on the night they chose
                await gathering(get_agent_fn, _party["host"], _party["guests"], _party.get("what", "a party"))
            elif _due(st, "call", CALL_PER_DAY, CALL_MIN_GAP_SECONDS) and _take_request_peek(
                    [aid for aid in social_roster() if aid != wb]):
                # calls replaced the group chat (2026-09-28). ONLY calls that came
                # from someone: his ask or their own REACH OUT. Nobody is asked
                # (Barry: "no prompting it to do it, it has to come fromm their
                # own minds"); a call they write into their own evening happens
                # in solo_moment.
                pool = [aid for aid in social_roster() if aid != wb]
                if _take_request_peek(pool):
                    await dm(get_agent_fn, phone=True, kind="call")
            # (the "dm" slot -- two people drawn by the office for a text or a visit -- was
            #  deleted 2026-09-28: "it has to be their choice". Texts and visits happen when
            #  their own evening says so, in solo_moment.)
            elif _due(st, "solo", SOLO_PER_DAY, SOLO_MIN_GAP_SECONDS):
                # an evening at home, as before -- NOT every night for everyone (Barry, 2026-09-28:
                # "no agent doing that every night. they work... none of this will happen, but it
                # could happen. seed or prompt nothing.")
                pool = [aid for aid in social_roster() if aid != wb]
                if pool:
                    await solo_moment(get_agent_fn, random.choice(pool))
        except Exception as e:
            reflect._log(f"homes loop error (living on): {e}")
