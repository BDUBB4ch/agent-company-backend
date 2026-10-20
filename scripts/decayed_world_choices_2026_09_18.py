"""Let Amara, Vivian and Elliot each CHOOSE their own eye out of Barry's
Decayed World reference, in their own words, and keep it as personality.

Barry, 2026-09-18: "make it her personality. choos artist style and whatever
else she wants. Vivian too and elliot let them choose based on their
personality."

So nothing is assigned. Each seat is handed the reference they were just taught
and asked which of it is THEIRS -- artists, vocabulary, lighting, weather,
whatever they want -- and why, in their own voice. Their answer goes into their
OWN section of their personality file verbatim (ingest.append_personality),
never into Barry's kernel, and nothing is suggested to them (tools-not-seeds).

Amara is additionally asked to pick ONE of the fifteen to draw for him -- her
pick, not ours.

Task turns (task:true), so none of this lands in their conversation threads.
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import ingest  # noqa: E402

API = "http://127.0.0.1:8420/api/chat"

ASK = (
    "Barry just gave the office his Decayed World reference -- the hyper "
    "realistic intricate decay artist list (Bulgarov, Kuciara, Ash Thorp, "
    "Beeple, Chadeisson, Feng Zhu), the keyword set, the chiaroscuro lighting "
    "note, and his fifteen rust and ruins prompts. Read it (it is on your "
    "shelf) and tell me which of it is actually YOURS.\n\n"
    "Not what is best, not what the office should use -- what YOU are drawn "
    "to. Which artist's eye, which of that vocabulary, what light, what "
    "weather, what kind of decay. Say why, in your own words. If some of it "
    "leaves you cold, say that too. A short paragraph, first person, no "
    "headings, no lists."
)

AMARA_EXTRA = (
    "\n\nThen, on a new line starting with 'I WOULD DRAW: ', name which ONE of "
    "his fifteen by its number and title you would actually make for him, and "
    "one sentence on why that one."
)

SEATS = [
    ("business", "BusinessOps", "Amara"),
    ("creative", "Creative", "Vivian"),
    ("movie", "MovieDirector", "Elliot"),
]


def ask(agent_id: str, message: str) -> dict:
    body = json.dumps({"agent_id": agent_id, "message": message,
                       "task": True}).encode()
    req = urllib.request.Request(API, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read())


def main() -> None:
    for agent_id, office, name in SEATS:
        msg = ASK + (AMARA_EXTRA if name == "Amara" else "")
        print(f"\n{'='*70}\n{name} ({office})\n{'='*70}")
        try:
            res = ask(agent_id, msg)
        except Exception as e:  # noqa: BLE001
            print(f"  FAILED: {e}")
            continue

        reply = (res.get("reply") or "").strip()
        print(f"  fell_back={res.get('bonsai_fell_back')} "
              f"tools={res.get('tool_calls')}")
        print(reply)

        if len(reply) < 80:
            print("  -> too short to keep, not written to personality")
            continue

        # Their words, verbatim, into THEIR section. Strip the draw-pick line
        # off Amara's -- that is a choice for one render, not a standing trait.
        keep = reply
        if "I WOULD DRAW:" in keep:
            keep = keep.split("I WOULD DRAW:")[0].strip()

        ok = ingest.append_personality(office, keep, when="2026-09-18")
        print(f"  -> personality append: {ok} "
              f"({len(ingest.own_section_of(office))} chars in their section)")


if __name__ == "__main__":
    main()
