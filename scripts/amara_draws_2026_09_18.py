"""Amara draws the one SHE chose out of Barry's Decayed World fifteen.

Barry, 2026-09-18: "I would love to see what Amara would draw for me" ->
"let Amara choose her own from that list."

Asked cold, she chose **#11 The Broken Throne -- A Church Drenched in Ruin
(Bleak, Snowy Winter)**, and said why in her own words: "It's the only one that
carries actual emotional gravity rather than just being something broken... The
others are decay for decay's sake; this one is about loss."

So this does not paste Barry's #11 back at the engine -- that would be HIM
drawing. It asks her to write it through the eye she just picked for herself
(Feng Zhu's weather weight, Ash Thorp's chiaroscuro, grief over texture) and
renders HER prompt. Result lands as her own approval for Barry to see.
"""
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

BASE = "http://127.0.0.1:8420"

ASK = (
    "You chose #11, The Broken Throne -- the ruined church in the snow -- out "
    "of Barry's Decayed World fifteen, because it is about loss rather than "
    "decay for its own sake. He wants to see it. Write the prompt you would "
    "actually render, through YOUR eye: the weather weight you said you wanted "
    "and the chiaroscuro that makes decay feel theatrical instead of ugly.\n\n"
    "It renders on Qwen, so: one flowing paragraph of plain prose, present "
    "tense, no weighted tags, no brackets, no negative block (inert there), no "
    "'no X' phrasing -- describe the frame as it IS. No people in it. Say the "
    "camera's position and what the light is doing. His words are the subject; "
    "the seeing is yours.\n\n"
    "Reply with the prompt ONLY, between a line reading ---PROMPT--- and a "
    "line reading ---END---. Nothing else."
)


def post(path: str, body: dict, timeout: int = 2400) -> dict:
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def main() -> None:
    res = post("/api/chat", {"agent_id": "business", "message": ASK,
                             "task": True}, timeout=900)
    reply = (res.get("reply") or "").strip()
    print(f"fell_back={res.get('bonsai_fell_back')}\n{reply}\n{'-'*70}")

    m = re.search(r"---PROMPT---\s*(.+?)\s*---END---", reply, re.S)
    prompt = (m.group(1) if m else reply).strip()
    prompt = re.sub(r"^```\w*\s*|\s*```$", "", prompt).strip()
    if len(prompt) < 120:
        print("her prompt came back too short -- not rendering")
        return

    # Her words only. Nothing appended: a prompt she did not write is not hers.
    print(f"RENDERING HER PROMPT ({len(prompt)} chars):\n{prompt}\n")
    out = post("/api/generate-image", {"prompt": prompt, "agent_id": "business"})
    print(json.dumps({k: v for k, v in out.items() if k != "image"}, indent=2)[:900])


if __name__ == "__main__":
    main()
