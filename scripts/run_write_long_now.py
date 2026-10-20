"""Run Ilnora's Long through the SECTION writer right now (2026-10-07) -- the same path her Saturday slot uses.
Goes through the live backend (/api/chat), so the backend must be up on the sections code. No GPU use beyond Bonsai."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
import video_queue  # noqa: E402

label = sys.argv[1] if len(sys.argv) > 1 else "Barry's Long tonight"
if "--resume" in sys.argv:                      # finish the saved draft (data/video_queue/last_draft_ilnora.json)
    import json
    import video_tool
    d = video_tool.last_draft("ilnora", 0) or {}
    v = d.get("draft") or {}
    assert v.get("parts"), "no saved draft to resume"
    v["format"] = "long"
    print("resuming", v.get("title"), sum(len(str(p.get("say", "")).split()) for p in v["parts"]), "words")
    ok = asyncio.run(video_queue.finish_long(v, label, v.get("_sources") or []))
else:
    ask = os.environ.get("LONG_ASK", "")          # Barry's words for this one video, if any
    ok = asyncio.run(video_queue.write_long(label, ask))
print("QUEUED" if ok else "NOT QUEUED -- see data/video_queue/queue.log")
