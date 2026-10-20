r"""One-off patch (2026-10-07 22:15): a length send-back on a sectioned Long now EXPANDS the shortest parts with a
locked SAY pass (the "whole video, longer" fix pass handed the video back unchanged twice at 1,491 words). Per-part
targets aim at 2,000 words so a pass lands over the 1,650 floor. The runner can resume from the saved draft."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def patch(path, pairs):
    t = open(path, encoding="utf-8").read()
    for a, b in pairs:
        assert t.count(a) == 1, (os.path.basename(path), a[:60])
        t = t.replace(a, b)
    open(path, "w", encoding="utf-8").write(t)
    print("ok", os.path.basename(path))


patch(os.path.join(ROOT, "backend", "video_queue.py"), [
(r'''LONG_TARGET_WORDS = 1800         # 1650 is the floor; aim a little over so one pass lands it''',
r'''LONG_TARGET_WORDS = 2000         # 1650 is the floor; she writes ~80% of a target, so aim well over'''),
(r'''async def write_long(slot_label: str) -> bool:''',
r'''async def expand_long(video: dict, slot_label: str, need: int) -> dict:
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


async def finish_long(video: dict, slot_label: str) -> bool:
    """The check, with a length send-back answered by expansion and any other send-back by one locked fix pass."""
    import video_tool
    before = len(queued())
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
            video = fixed
            video["format"] = "long"
    _log(f"{slot_label}: Long did not queue after the fix passes")
    return False


async def write_long(slot_label: str) -> bool:'''),
(r'''    video = _assemble(plan, says)
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
    return False''',
r'''    video = _assemble(plan, says)
    # 4. the same check as always; short = expand the shortest parts; anything else = one locked fix pass
    return await finish_long(video, slot_label)'''),
])

patch(os.path.join(ROOT, "scripts", "run_write_long_now.py"), [
(r'''label = sys.argv[1] if len(sys.argv) > 1 else "Barry's Long tonight"
ok = asyncio.run(video_queue.write_long(label))''',
r'''label = sys.argv[1] if len(sys.argv) > 1 else "Barry's Long tonight"
if "--resume" in sys.argv:                      # finish the saved draft (data/video_queue/last_draft_ilnora.json)
    import json
    import video_tool
    d = video_tool.last_draft("ilnora", 0) or {}
    v = d.get("draft") or {}
    assert v.get("parts"), "no saved draft to resume"
    v["format"] = "long"
    print("resuming", v.get("title"), sum(len(str(p.get("say", "")).split()) for p in v["parts"]), "words")
    ok = asyncio.run(video_queue.finish_long(v, label))
else:
    ok = asyncio.run(video_queue.write_long(label))'''),
])
