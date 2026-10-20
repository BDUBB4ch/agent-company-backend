"""Taliyah's reach gate, both directions, against her REAL shelf.

Barry, 2026-09-18: "Taliyah needs the research thing on hand. the other skills
she should only reach for if i asked her something she doesnt know outright...
That way our regular conversations are still speedy."

Three things are being asserted, and the middle one is the whole point:
  1. ORDINARY CONVERSATION recalls nothing -- this is the band that changed.
     Every case here is a message that WOULD have pulled 13-17K chars before.
  2. A REAL ASK still gets her full shelf, up to three documents.
  3. The research/hand-off door is reachable in BOTH states.

Run after any change to _REAL_ASK_RE, SEAT_REACH_ONLY or ALWAYS_REACHABLE.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "backend"))

import recall    # noqa: E402

SEAT = "Taliyah"

# Ordinary conversation. Recall must be SILENT -- not "small", silent.
QUIET = [
    "i cant sleep again",
    "i been at it since 6",
    "im tired of this business",
    "rough day, the store did nothing again",
    "why you talking like that",
    "whats up",
    "whats good",
    "morning",
    "lol you good?",
    "i just need to sit here for a minute",
    "my mind stays racing",
    "you up?",
    "that was a long ass day",
    "i dont even know why i keep going",
]

# He is asking her something. She may reach for the shelf.
ASK = [
    "how do i keep a cutting alive in coco",
    "whats the difference between silica and cal mag",
    "do you know anything about SMR drives",
    "explain how the tax thing works for an llc",
    "look up what those backpacks go for",
    "can you research the bag supplier thing",
    "help me figure out what to do about the store",
    "teach me how to read a margin",
]

# The research door -- must work whether or not the gate is open.
RESEARCH = [
    "put my idea together and hand it to the team",
    "can you file this idea for the team",
    "ask priya to look into it",
    "i want to delegate this one",
]

RESEARCH_DOC = "working-with-your-teammates"


def main() -> int:
    fails = 0

    print("QUIET -- ordinary conversation, must recall nothing:")
    for msg in QUIET:
        _, titles = recall.recall_for_message(SEAT, msg)
        ok = not titles
        fails += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FIRED':<5} | {msg[:42]:<44} {titles}")

    print("\nASK -- he asked her something, shelf is allowed:")
    for msg in ASK:
        ask = recall._is_real_ask(msg)
        fails += 0 if ask else 1
        _, titles = recall.recall_for_message(SEAT, msg)
        print(f"  {'PASS' if ask else 'BLOCKED':<7} | gate {'open ' if ask else 'shut '}"
              f"| {msg[:38]:<40} {titles[:3]}")

    print("\nRESEARCH -- the door he wants on hand:")
    for msg in RESEARCH:
        _, titles = recall.recall_for_message(SEAT, msg)
        ok = RESEARCH_DOC in titles
        fails += 0 if ok else 1
        print(f"  {'PASS' if ok else 'MISS':<5} | {msg[:42]:<44} {titles[:3]}")

    # Nothing above may change any other seat.
    print("\nNO SPILL -- another seat is untouched by the gate:")
    for office, msg in [("BusinessOps", "whats our margin on mgo 10"),
                        ("Marketing", "i been at it since 6"),
                        ("Operations", "i cant sleep again")]:
        closed = office in recall.SEAT_REACH_ONLY
        fails += 1 if closed else 0
        _, titles = recall.recall_for_message(office, msg)
        print(f"  {'PASS' if not closed else 'GATED':<5} | {office:<12} "
              f"{msg[:30]:<32} {titles[:2]}")

    print()
    if fails:
        print(f"⚠️ {fails} failure(s)")
        return 1
    print("ALL PASS -- quiet on conversation, open on a question, "
          "research always reachable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
