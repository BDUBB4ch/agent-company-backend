"""Show the rest of the office Barry's Decayed World list and let each of them pick (2026-09-29).

Barry: "you were just supposed to show them the list and let them pick one and make it their own"
+ "they all are supposed to pick from that list and make it their own style, they can even alter it as
well, but it all has the be hyper realistic always".

Same shape as scripts/decayed_world_choices_2026_09_18.py (Amara, Vivian, Elliot; Sophie and Taliyah
were asked the same day): a task turn per seat, their answer VERBATIM into their own section of their
personality (ingest.append_personality -- append-only, backed up), never into Barry's kernel. Nothing
suggested. Seats that already picked in their own words (Amara, Taliyah, Elliot) are not asked again.
Vivian is asked again: her 09-18 answer never reached her personality (her own section is empty).
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import ingest  # noqa: E402

API = "http://127.0.0.1:8420/api/chat"

ASK = (
    "Barry's Decayed World reference is on your shelf -- the hyper realistic intricate decay artist list "
    "(Bulgarov, Kuciara, Ash Thorp, Beeple, Chadeisson, Feng Zhu), the keyword set, the chiaroscuro lighting "
    "note, and his fifteen rust and ruins prompts. Read it.\n\n"
    'Barry says: "they all are supposed to pick from that list and make it their own style, they can even '
    'alter it as well, but it all has the be hyper realistic always" -- and: "they can pick all that '
    'applies based on their personality, mix and blend to create their own style".\n\n'
    "So pick whatever of it applies to you -- one thing or several -- and mix and blend it into your own "
    "style, changed however you want. Not what is best, not what the office should use -- what YOU are drawn "
    "to, and what you would do with it to make it yours. Say why, in your own words. A short paragraph, "
    "first person, no headings, no lists."
)

SEATS = [
    ("cio", "CIO", "Victor"),
    ("operations", "Operations", "Priya"),
    ("legal", "Legal", "Marcus"),
    ("marketing", "Marketing", "Derek"),
    ("creative", "Creative", "Vivian"),
    ("engineer", "Engineer", "Sophie"),
    ("ilnora", "ilnora", "Ilnora"),
]


def ask(agent_id: str, message: str) -> dict:
    body = json.dumps({"agent_id": agent_id, "message": message, "task": True}).encode()
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1200) as r:
        return json.loads(r.read())


def main() -> None:
    for agent_id, office, name in SEATS:
        print(f"\n{'=' * 70}\n{name} ({office})\n{'=' * 70}", flush=True)
        try:
            res = ask(agent_id, ASK)
        except Exception as e:  # noqa: BLE001
            print(f"  FAILED: {e}", flush=True)
            continue
        reply = (res.get("reply") or "").strip()
        print(f"  fell_back={res.get('bonsai_fell_back')}", flush=True)
        print(reply, flush=True)
        if len(reply) < 80 or reply.startswith("["):
            print("  -> too short / not a real answer, not written to personality", flush=True)
            continue
        ok = ingest.append_personality(office, reply, when="2026-09-29")
        print(f"  -> personality append: {ok} ({len(ingest.own_section_of(office) or '')} chars in their section)",
              flush=True)


if __name__ == "__main__":
    main()
