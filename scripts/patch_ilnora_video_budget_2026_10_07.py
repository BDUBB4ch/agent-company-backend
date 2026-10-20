r"""One-off patch (2026-10-07 21:12, Barry: "make the big budget only for actual video making"): Ilnora's video-turn
budget (4096 thinking / 16384 reply / 8 tool rounds) only when a video is actually being made -- not whenever the
word "videos" appears (a one-line outfit note ran 6 tool rounds and 31 minutes)."""
import os

p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", "main.py")
t = open(p, encoding="utf-8").read()


def rep(a, b):
    global t
    assert t.count(a) == 1, a[:70]
    t = t.replace(a, b)


rep(r'''        if req.agent_id == "ilnora" and not _is_personal and (
                (req.task and "make_video" in (req.message or ""))
                or re.search(r"\b(video|videos|vid|vids|short|shorts|long|longform)\b", req.message or "", re.I)):
            # (2026-10-07) also when BARRY asks her for a video himself in her office window
''',
r'''        if req.agent_id == "ilnora" and not _is_personal and _ilnora_video_making(req):
            # (2026-10-07) also when BARRY asks her for a video himself in her office window -- but only when a
            # video is actually being made (Barry 21:12: "make the big budget only for actual video making":
            # a one-line note with the word "videos" in it ran 6 tool rounds and 31 minutes)
''')

rep(r'''        elif req.agent_id == "ilnora" and not _is_personal:
            # (2026-10-07, Barry: "give her the 8 rounds") -- "keep scouting" had no video word, so she got 3 rounds,
            # spent them reading her library, and the out-of-rounds pass left her a "let me scout" stub twice.
            bonsai_llm.tool_rounds_override.set(8)
''', '')

rep(r'''def _quick_reply_ask(message: str, agent_id: str | None = None) -> bool:''',
r'''_VIDEO_WORD = r"(?:video|videos|vid|vids|short|shorts|longform|long\s+form|long|deep\s+dive|script)"
_VIDEO_VERB = r"(?:make|write|plan|create|build|start|redo|rewrite|cut|draft|send|check|finish|do|scout|pick|choose)"


def _ilnora_video_making(req) -> bool:
    """Is this turn actually MAKING a video (2026-10-07, Barry: "make the big budget only for actual video making")?
    True for her scheduled jobs, the office's send-backs, an ask that pairs a doing-verb with a video word in one
    sentence ("make a long video", "plan the next shorts"), and a short follow-up while her last reply was a plan or
    a video ("make it.", "keep scouting", "swap the plants"). A note that merely mentions videos is not."""
    m = (req.message or "").strip()
    if not m:
        return False
    if req.task and "make_video" in m:
        return True
    if m.startswith("The office checked your video"):
        return True
    if (re.search(rf"\b{_VIDEO_VERB}\w*\b[^.?!\n]{{0,60}}\b{_VIDEO_WORD}\b", m, re.I)
            or re.search(rf"\b{_VIDEO_WORD}\b[^.?!\n]{{0,40}}\b{_VIDEO_VERB}\w*\b", m, re.I)):
        return True
    if len(m.split()) <= 8:
        try:
            with memory.get_db() as conn:
                row = conn.execute("SELECT content FROM conversations WHERE agent_id = 'ilnora' AND role = 'agent' "
                                   "ORDER BY id DESC LIMIT 1").fetchone()
            last = (row[0] if row else "") or ""
        except Exception:  # noqa: BLE001
            last = ""
        return bool(re.search(r"THE PLAN|\"parts\"|make_video|check_video|\bvideo\b", last, re.I))
    return False


def _quick_reply_ask(message: str, agent_id: str | None = None) -> bool:''')

open(p, "w", encoding="utf-8").write(t)
print("main ok")
