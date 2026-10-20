r"""One-off patch (2026-10-08, Barry: "we may need someone to check her work or teach her to proof read her work"):
HER PROOFREAD TURN after every build. The office pulls one frame per part from the finished MP4, has its eyes
(media_understanding.describe_image, the local vision model) say literally what is on screen, then SHE judges her
own work against her plan -- same outfit throughout, the plant looks like the species, nothing written on screen,
she looks like herself -- and answers as locked JSON. The review goes to Barry's DESK with the frames; the job keeps
it. Nothing is re-rendered by itself (his call)."""
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
(r'''async def _build_one(job: dict) -> None:''',
r'''REVIEW_SCHEMA = {"type": "object", "required": ["ok", "problems"], "properties": {
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
                "labels or captions anywhere; anything odd (extra fingers, warped face, a second person). Report only "
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
           f"screen; you look like yourself; nobody else in the picture. Answer as JSON only: "
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


async def _build_one(job: dict) -> None:'''),
(r'''    if isinstance(ok, str) and os.path.isfile(ok):
        # HIS FOLDER (Barry 2026-10-03: "just leave them all in a folder on my desktop, Ilnora's Videos")''',
r'''    if isinstance(ok, str) and os.path.isfile(ok):
        try:
            job["review"] = await proofread(job, ok)       # 2026-10-08: she proofreads before Barry sees it
        except Exception as exc:  # noqa: BLE001
            _log(f"proofread crashed: {type(exc).__name__}: {exc}")
        # HIS FOLDER (Barry 2026-10-03: "just leave them all in a folder on my desktop, Ilnora's Videos")'''),
])
