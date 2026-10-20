r"""One-off patch (2026-10-08): write_long takes Barry's words for one video (ask); every "1650 words" the office
tells her becomes the new floor (1950); the runner passes LONG_ASK from the environment."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def patch(path, pairs):
    t = open(path, encoding="utf-8").read()
    for a, b in pairs:
        assert t.count(a) >= 1, (os.path.basename(path), a[:60])
        t = t.replace(a, b)
    open(path, "w", encoding="utf-8").write(t)
    print("ok", os.path.basename(path))


patch(os.path.join(ROOT, "backend", "video_queue.py"), [
(r'''async def write_long(slot_label: str) -> bool:''',
 r'''async def write_long(slot_label: str, ask: str = "") -> bool:'''),
(r'''                       "your own parts. No script yet; the office asks for it next, part by part.\n\n" + brief,''',
 r'''                       "your own parts. No script yet; the office asks for it next, part by part.\n\n"
                       + (f"FROM BARRY, FOR THIS VIDEO:\n{ask}\n\n" if ask else "") + brief,'''),
(r'''1650 words''', r'''1950 words'''),
])

patch(os.path.join(ROOT, "scripts", "run_write_long_now.py"), [
(r'''    ok = asyncio.run(video_queue.write_long(label))''',
 r'''    ask = os.environ.get("LONG_ASK", "")          # Barry's words for this one video, if any
    ok = asyncio.run(video_queue.write_long(label, ask))'''),
])
