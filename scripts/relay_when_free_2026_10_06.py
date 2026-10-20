"""Relay Barry's words to Ilnora's office window once her builds free the card (Bonsai is off it while they run)."""
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLAG = os.path.join(ROOT, "data", "reel_building.flag")
MSG = ('From Barry (relayed by Claude, his exact words): "let the scenes also tell the story, and no texts. '
       'tell her that"')
def busy():
    return os.path.exists(FLAG) or any(
        json.load(open(os.path.join(ROOT, "data", "video_queue", f), encoding="utf-8")).get("status") == "building"
        for f in os.listdir(os.path.join(ROOT, "data", "video_queue")) if f.startswith("job_"))


time.sleep(120)
quiet = 0
while quiet < 5:            # 5 quiet minutes in a row: the second build (which starts ~30 s after the first) is done too
    quiet = 0 if busy() else quiet + 1
    time.sleep(60)
req = urllib.request.Request("http://127.0.0.1:8420/api/chat",
                             data=json.dumps({"agent_id": "ilnora", "message": MSG, "personal": False}).encode(),
                             headers={"Content-Type": "application/json"})
r = json.loads(urllib.request.urlopen(req, timeout=2400).read()).get("reply", "")
open(os.path.join(ROOT, "data", "video_queue", "relay_reply_2026-10-06.txt"), "w", encoding="utf-8").write(r)
