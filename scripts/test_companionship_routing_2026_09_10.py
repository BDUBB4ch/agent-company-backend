"""Does recall put the right document in front of Taliyah?

Behaviour test against her real shelf. Two things it protects:
  1. the right doc arrives for the way Barry actually types;
  2. ordinary talk pulls NOTHING -- she is his friend, and a greeting that
     drags 14K of craft doc into the prompt is the failure mode here.
Run after ANY edit to a USE WHEN line in knowledge/companionship/.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import recall  # noqa: E402

OFFICE = "Taliyah"

# ⚠️ REWRITTEN 2026-09-18 AFTER BARRY NARROWED WHEN SHE REACHES AT ALL.
# "the other skills she should only reach for if i asked her something she
# doesnt know outright... That way our regular conversations are still speedy."
# recall.SEAT_REACH_ONLY implements that: her shelf is reachable on a QUESTION
# and closed on ordinary talk. Seven cases that used to live here -- "i cant
# sleep again", "rough day man, im just done", "you sound corny", "you even
# listening to me", "i just need to vent", "you just agreeing with me", "why
# you talking like that" -- are statements, not asks, so they now correctly
# recall NOTHING and have MOVED into QUIET below.
# They are kept listed rather than deleted because the day this file stops
# recording that these were once expected to fire is the day somebody "fixes"
# the gate back.
# A battery that keeps failing on purpose teaches everyone to ignore it.
#
# message -> a word that must appear in a recalled document's title
CASES = [
    ("do you remember what i said about the tent", "remember"),
    ("dont forget that", "remember"),
    ("be honest, is this a bad idea", "truth"),
    ("been thinking about something, hear me out", "thinking"),
    ("im stuck between two options", "thinking"),
    ("how does your memory even work", "own-life"),
]

# Small talk and everyday messages must recall nothing from her shelf.
# KNOWN FLOOR, not a bug: even at her lowered seat floor of 7, a message with
# exactly one scorable word after tokenizing cannot clear the bar. Printed so
# the limit stays visible, never asserted.
FLOOR = ["why do you always do that", "you get me",
         # tokenizes to exactly ['been'], which his vents also carry --
         # routing it would steal "i been at it since 6" from the
         # hard-moment doc, and that trade is not worth making.
         "what you been up to when im not here"]

QUIET = [
    "you up",
    "morning",
    "lol",
    "nah im good",
    "what you doing",
    # Moved here 2026-09-18 by his ruling (see the note on CASES). These are
    # him TALKING to her, not asking her anything -- she answers as herself,
    # fast, with no document in the turn.
    "you even listening to me",
    "i just need to vent for a second",
    "rough day man, im just done",
    "i cant sleep again",
    "you just agreeing with me",
    "why you talking like that",
    "you sound corny",
]

HER_DOCS = ("Listening", "Remembering", "Being There", "Telling", "Thinking",
            "How You Talk", "Your Memory", "How Taliyah")


def titles_for(message: str) -> list[str]:
    _block, titles = recall.recall_for_message(OFFICE, message)
    return titles


def main() -> None:
    fails = []
    for msg, want in CASES:
        titles = titles_for(msg)
        ok = any(want.lower() in t.lower() for t in titles)
        print(f"{'PASS' if ok else 'FAIL'}  {msg!r}\n        -> {titles or '(nothing)'}")
        if not ok:
            fails.append(msg)
    for msg in FLOOR:
        print(f"note  (known floor) {msg!r} -> {titles_for(msg) or 'nothing'}")
    for msg in QUIET:
        titles = titles_for(msg)
        noisy = [t for t in titles if t.startswith(HER_DOCS)]
        ok = not noisy
        print(f"{'PASS' if ok else 'FAIL'}  (quiet) {msg!r} -> {noisy or 'nothing'}")
        if not ok:
            fails.append(msg)
    print()
    if fails:
        print(f"{len(fails)} FAILING")
        raise SystemExit(1)
    print(f"companionship routing battery: ALL PASS ({len(CASES) + len(QUIET)} cases)")


if __name__ == "__main__":
    main()
