"""Battery for main._quick_reply_ask (2026-09-08). Run after ANY change to
_QUICK_WORK_RE or the thresholds. Loads the classifier from main.py's source
without importing main (which builds the app)."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read()
start = src.index("_QUICK_WORK_RE = re.compile(")
end = src.index("    return True", start) + len("    return True")
ns = {"re": re, "TALIYAH_ID": "taliyah"}
exec(src[start:end], ns)
q = ns["_quick_reply_ask"]

CASES = {
    # quick (True) -- casual, short, no work intent
    "cool, ill grab some row cover this week": True,
    "its in the ground, i cant move it": True,
    "morning derek": True,
    "lol yeah": True,
    "thanks": True,
    "hows it going?": True,
    "say ok": True,
    "the plant looks better today": True,
    "nah im good": True,
    # full budget (False) -- work intent, numbers, office questions, shots
    "write me a CTA for the Bionova email": False,
    "why are we getting clicks but no orders": False,
    "hows the systems?": False,
    "give me 3 ad concepts for SiLution": False,
    "what should the button say": False,
    "it hit 85 degrees in the tent": False,
    "can you check the store": False,
    "Shots 2 and 3, please": False,
    "plan the next 90 days": False,
    "how do i get my old customers to reorder": False,
    "this is a very long message that goes on and on about nothing in particular but is certainly longer than one hundred and forty characters total": False,
}
bad = [(m, want, q(m)) for m, want in CASES.items() if q(m) != want]
if bad:
    for m, want, got in bad:
        print(f"FAIL {m!r}: want {want} got {got}")
    raise SystemExit(1)
print(f"quick-reply battery: ALL PASS ({len(CASES)} cases)")
