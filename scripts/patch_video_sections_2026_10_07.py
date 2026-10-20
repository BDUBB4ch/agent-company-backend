r"""One-off patch (2026-10-07 21:40, Barry: "build both, the grammar lock and the sections").

GRAMMAR LOCK: a Bonsai pass can be forced to answer as JSON matching a schema (llama.cpp response_format). Set per
request via bonsai_llm.json_schema_override; /api/chat takes an optional "json_schema" (loopback-only API). A locked
pass runs with thinking off and no tools -- the grammar would otherwise fight the <think> block.

SECTIONS (AgentWrite / LongWriter method): a Long is no longer asked for in one breath. video_queue.write_long:
  1. research turn (thinking + tools on, no grammar) -> her notes
  2. PLAN pass (locked): title, mood, caption, hashtags, 12-18 parts -- what each covers, what is on screen, her shot
  3. SAY passes (locked), 4 parts at a time, with the lines already written in front of her and a per-part target
  4. assemble -> video_tool.check (the same check as always); a send-back = one locked fix pass, up to 2
Her words are hers at every step; the office only asks in smaller pieces and refuses prose where a video is due.
A Short that comes back with no video gets ONE locked pass instead of the old text nudge.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def patch(path, pairs):
    t = open(path, encoding="utf-8").read()
    for a, b in pairs:
        assert t.count(a) == 1, (os.path.basename(path), a[:60])
        t = t.replace(a, b)
    open(path, "w", encoding="utf-8").write(t)
    print("ok", os.path.basename(path))


# ---------------------------------------------------------------- bonsai_llm: the lock
patch(os.path.join(ROOT, "backend", "bonsai_llm.py"), [
(r'''loop_guard: _cv.ContextVar[bool] = _cv.ContextVar("loop_guard", default=True)''',
r'''loop_guard: _cv.ContextVar[bool] = _cv.ContextVar("loop_guard", default=True)
# GRAMMAR LOCK (2026-10-07, Barry: "build both, the grammar lock and the sections"): a JSON schema the reply MUST
# match (llama.cpp response_format). The pass runs with thinking off and no tools. Used by video_queue's section
# writer so a script can only come back as a script -- never "I've written it to ~1,747 words".
json_schema_override: _cv.ContextVar[dict | None] = _cv.ContextVar("json_schema_override", default=None)'''),
(r'''            if not use_thinking:
                request_body.pop("thinking_budget_tokens", None)
                request_body.pop("thinking_budget_message", None)
                request_body["chat_template_kwargs"] = {"enable_thinking": False}
            if tools:
                request_body["tools"] = tools''',
r'''            _schema = json_schema_override.get()
            if _schema:
                use_thinking = False                 # the grammar would fight the <think> block
                tools = None                         # a locked pass answers, it does not call
                request_body["response_format"] = {"type": "json_object", "schema": _schema}
            if not use_thinking:
                request_body.pop("thinking_budget_tokens", None)
                request_body.pop("thinking_budget_message", None)
                request_body["chat_template_kwargs"] = {"enable_thinking": False}
            if tools:
                request_body["tools"] = tools'''),
])

# ---------------------------------------------------------------- main: /api/chat takes a schema
patch(os.path.join(ROOT, "backend", "main.py"), [
(r'''    personal: bool = False
    # Set when Barry clicked a specific FOR-BARRY note and is answering IT''',
r'''    personal: bool = False
    # GRAMMAR LOCK (2026-10-07): the office's own callers (video_queue's section writer) can demand the reply as
    # JSON matching this schema. Loopback-only API; the decks never set it.
    json_schema: dict | None = None
    # Set when Barry clicked a specific FOR-BARRY note and is answering IT'''),
(r'''        if req.agent_id == "ilnora" and not _is_personal and _ilnora_video_making(req):''',
r'''        bonsai_llm.json_schema_override.set(req.json_schema or None)
        if req.agent_id == "ilnora" and not _is_personal and _ilnora_video_making(req):'''),
])

# ---------------------------------------------------------------- video_queue: the section writer
patch(os.path.join(ROOT, "backend", "video_queue.py"), [
(r'''async def _ask(message: str) -> dict:
    async with httpx.AsyncClient(timeout=2400) as cx:
        r = await cx.post("http://127.0.0.1:8420/api/chat",
                          json={"agent_id": AGENT, "message": message, "task": True, "personal": False,
                                "activity": "making videos for tonight"})
    r.raise_for_status()
    return r.json() or {}''',
r'''async def _ask(message: str, schema: dict | None = None, activity: str = "making videos for tonight") -> dict:
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
LONG_TARGET_WORDS = 1800         # 1650 is the floor; aim a little over so one pass lands it
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


async def write_long(slot_label: str) -> bool:
    """The week's Long, in sections. True when it queued."""
    import video_tool
    before = len(queued())
    brief = _brief(slot_label, "long")
    # 1. research -- thinking and tools on, no grammar: her notes
    notes = await _ask(f"Scheduled job from the office ({slot_label}): tonight you make a Long video "
                       f"(widescreen, {LONG_MINUTES} minutes or more spoken, 1650 words or more). FIRST, research it: "
                       "pick the plant(s) with the steps in your make-video-masterfully skill, read the sections in "
                       "your library and anything on PubMed you will lean on, and reply with your NOTES -- the plant(s), "
                       "the facts you will use (each with where it came from), the story's shape, and your look for "
                       "your own parts. No script yet; the office asks for it next, part by part.\n\n" + brief,
                       activity="researching tonight's Long")
    _log(f"{slot_label}: research notes {len((notes.get('reply') or '').split())} words")
    # 2. the plan, locked
    data = await _ask("Now plan the Long from your notes, as JSON only: title, mood (spooky|calm|upbeat|mystic), "
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
               f"talk on camera; the whole video must reach 1650 words. Facts only from your notes.\n\n"
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
    # 4. the same check as always; a send-back = one locked fix pass, twice at most
    for _round in range(3):
        res = await _submit(video, "long")
        if res.get("queued") or res.get("started") or len(queued()) > before:
            _log(f"{slot_label}: Long queued in sections ({sum(len(p['say'].split()) for p in video['parts'])} words)")
            return True
        fix = res.get("fix_this")
        if not fix or _round == 2:
            break
        _log(f"{slot_label}: sent back ({str(fix)[:120]}) -- one locked fix pass")
        data = await _ask("The office checked your video and sent it back for one thing: " + str(fix)
                          + "\n\nHere is the whole video. Change only that and answer with the whole video as JSON "
                            "(title, format, mood, parts, caption, hashtags).\n```json\n"
                          + json.dumps(video, ensure_ascii=False) + "\n```", schema=VIDEO_SCHEMA,
                          activity="fixing tonight's Long")
        fixed = _json_reply(data)
        if fixed and fixed.get("parts"):
            video = fixed
            video["format"] = "long"
    _log(f"{slot_label}: Long did not queue after the fix passes")
    return False'''),
# make_one: Longs go through sections; a Short with no video gets one locked pass
(r'''async def make_one(form: str, slot_label: str, budget_note: str = "", use_plan: bool = True) -> bool:
    """One video turn: she writes it; the office checks it with her tool's own checks and queues it."""
    import video_tool
    before = len(queued())''',
r'''async def make_one(form: str, slot_label: str, budget_note: str = "", use_plan: bool = True) -> bool:
    """One video turn: she writes it; the office checks it with her tool's own checks and queues it."""
    import video_tool
    if form == "long":
        return await write_long(slot_label)                  # 2026-10-07: in sections, grammar-locked
    before = len(queued())'''),
(r'''        else:
            _log(f"{slot_label}: reply had no video, asking once more. It began: "
                 + " ".join((data.get("reply") or "").split())[:200])
            data = await _ask("Your reply had no video in it, so nothing was queued. Send the whole video now: call "
                              "make_video, or write it as one JSON block (title, format, mood, parts, caption, "
                              "hashtags).")''',
r'''        else:
            _log(f"{slot_label}: reply had no video, asking once more (locked). It began: "
                 + " ".join((data.get("reply") or "").split())[:200])
            # 2026-10-07: one grammar-locked pass -- the reply can only be the video
            data = await _ask("Your reply had no video in it, so nothing was queued. Answer with the whole video now "
                              "as JSON: title, format, mood, parts (say, show, shot, plant, motion, move), caption, "
                              "hashtags.", schema=VIDEO_SCHEMA)
            if _json_reply(data) and not _video_json(data.get("reply") or ""):
                data = dict(data, reply="```json\n" + json.dumps(_json_reply(data), ensure_ascii=False) + "\n```")'''),
])
