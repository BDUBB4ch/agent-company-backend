r"""One-off patch (2026-10-08): wire the FACT NET into the section writer. The research turn's "sources" (the exact
tool text she read) travel with the Long; after assembly every sentence is checked; flagged parts go back to her
(locked SAY pass) up to 2 rounds; what is still flagged is logged and written into the job for Barry."""
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
# finish_long takes the sources and runs the fact net before the ordinary check
(r'''async def finish_long(video: dict, slot_label: str) -> bool:
    """The check, with a length send-back answered by expansion and any other send-back by one locked fix pass."""
    import video_tool
    before = len(queued())''',
r'''async def fact_pass(video: dict, sources: list[str], slot_label: str) -> dict:
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
        msg = (fact_net.send_back_text(res["flags"])
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
    video = await fact_pass(video, sources or [], slot_label)'''),
# the research turn's sources are kept and handed to finish_long
(r'''    _log(f"{slot_label}: research notes {len((notes.get('reply') or '').split())} words")''',
r'''    sources = [s for s in (notes.get("sources") or []) if s]
    _log(f"{slot_label}: research notes {len((notes.get('reply') or '').split())} words, "
         f"{len(sources)} sources ({sum(len(s.split()) for s in sources)} words)")'''),
(r'''    video = _assemble(plan, says)
    # 4. the same check as always; short = expand the shortest parts; anything else = one locked fix pass
    return await finish_long(video, slot_label)''',
r'''    video = _assemble(plan, says)
    video["_sources"] = sources
    # 4. the fact net, then the same check as always; short = expand the shortest parts; else one locked fix pass
    return await finish_long(video, slot_label, sources)'''),
# the fact flags and sources ride on the queued job (never into the builder's scenes)
(r'''def enqueue(agent_id: str, pkg: dict) -> dict:
    os.makedirs(QDIR, exist_ok=True)''',
r'''def enqueue(agent_id: str, pkg: dict) -> dict:
    os.makedirs(QDIR, exist_ok=True)
    for k in ("_fact_flags", "_sources"):
        pkg.pop(k, None)'''),
])

# the runner's --resume path hands the saved sources along
patch(os.path.join(ROOT, "scripts", "run_write_long_now.py"), [
(r'''    ok = asyncio.run(video_queue.finish_long(v, label))''',
r'''    ok = asyncio.run(video_queue.finish_long(v, label, v.get("_sources") or []))'''),
])
