r"""One-off patch (2026-10-08 11:20): when Barry names the video (a redo, a plant), it is THE ASSIGNMENT -- the research
turn opens with it and the plan is held to those plants (the 10:30 redo of bloodroot came back as a 10-plant witch
garden). Also: the fix passes replace the video dict, which dropped the captured sources -- keep them."""
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
(r'''    notes = await _ask(f"Scheduled job from the office ({slot_label}): tonight you make a Long video "
                       f"(widescreen, {LONG_MINUTES} minutes or more spoken, 1950 words or more). FIRST, research it: "
                       "pick the plant(s) with the steps in your make-video-masterfully skill, read the sections in "''',
r'''    notes = await _ask((f"THIS VIDEO, FROM BARRY: {ask}\n\n" if ask else "")
                       + f"Scheduled job from the office ({slot_label}): tonight you make a Long video "
                       f"(widescreen, {LONG_MINUTES} minutes or more spoken, 1950 words or more). FIRST, research it: "
                       + ("it is the video Barry named above -- that plant, that story; " if ask else
                          "pick the plant(s) with the steps in your make-video-masterfully skill, ")
                       + "read the sections in "'''),
(r'''    data = await _ask("Now plan the Long from your notes, as JSON only: title, mood (spooky|calm|upbeat|mystic), "''',
r'''    data = await _ask((f"THIS VIDEO, FROM BARRY: {ask}\n\n" if ask else "")
                      + "Now plan the Long from your notes, as JSON only: title, mood (spooky|calm|upbeat|mystic), "'''),
(r'''        fixed = _json_reply(data)
        if fixed and fixed.get("parts"):
            video = fixed
            video["format"] = "long"
    _log(f"{slot_label}: Long did not queue after the fix passes")''',
r'''        fixed = _json_reply(data)
        if fixed and fixed.get("parts"):
            fixed["_sources"] = video.get("_sources") or []        # the captured sources ride along
            video = fixed
            video["format"] = "long"
    _log(f"{slot_label}: Long did not queue after the fix passes")'''),
])
