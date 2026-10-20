"""Run Barry's video ask for Ilnora through the office's own ask path (video_queue.barry_asked -- what main.py's ASK
DOOR runs), for an ask whose wording the door did not catch. His words go in verbatim via BARRY_ASK. Goes through the
live backend (/api/chat); builds are held while she writes and released after. Usage:
    BARRY_ASK="..." venv/Scripts/python.exe scripts/run_barry_ask_now.py long [n]"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
import video_queue  # noqa: E402

ask = os.environ.get("BARRY_ASK", "").strip()
assert ask, "BARRY_ASK (his exact words) is required"
form = sys.argv[1] if len(sys.argv) > 1 else "long"
n = int(sys.argv[2]) if len(sys.argv) > 2 else 1
asyncio.run(video_queue.barry_asked(n, form, ask))
print("done -- see data/video_queue/queue.log")
