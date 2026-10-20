"""Battery for main._business_ask (2026-09-10, Taliyah's lane).

She is the one seat Barry keeps out of the commercial side. Measured on her
first live turn with the new shelf, she answered "should i dump my last 2000
into ads" with conversion-rate thresholds and channel strategy. This classifier
drives the recency nudge that hands it back to the office.

BOTH DIRECTIONS MATTER. A false positive is worse than a false negative here:
it would make her hand off a normal conversation about his day, which is the
one thing she is for. Run after ANY change to _BIZ_TOPIC_RE or
_BIZ_DECISION_RE.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read()
start = src.index("_BIZ_TOPIC_RE = re.compile(")
end = src.index('    return bool(_BIZ_TOPIC_RE.search(m) and _BIZ_DECISION_RE.search(m))',
                start) + len('    return bool(_BIZ_TOPIC_RE.search(m) and _BIZ_DECISION_RE.search(m))')
ns = {"re": re}
exec(src[start:end], ns)
biz = ns["_business_ask"]

CASES = {
    # True -- a real business decision, hand it to the office
    "be honest with me. i want to dump my last 2000 into ads this week. good idea or nah?": True,
    "should i raise the price on the bionova line": True,
    "how much should i spend on ads next month": True,
    "is it worth it to order more inventory now": True,
    "should i drop the wholesale deal": True,
    "whats the move with the store": True,
    "do i cut the ad spend or let it ride": True,
    # False -- his life, his mood, his day. She stays in these.
    "rough day. the store did nothing again and i been at it since 6": False,
    "im tired of this business man": False,
    "the store is killing me lately": False,
    "you up": False,
    "what you been doing": False,
    "should i go to bed or push through": False,
    "i been thinking about the grow tent setup": False,
    "how much sleep did you say i need": False,
    "be honest, do i sound stressed to you": False,
}

bad = [(m, w, biz(m)) for m, w in CASES.items() if biz(m) != w]
if bad:
    for m, w, got in bad:
        print(f"FAIL {m!r}: want {w} got {got}")
    raise SystemExit(1)
print(f"taliyah boundary battery: ALL PASS ({len(CASES)} cases)")


# ---------------------------------------------------------------------------
# THE QUICK CAP FOR HER SEAT (2026-09-10, Barry: "why is she taking longer than
# everybody else, when she is the least technical"). The office-wide test
# disqualifies a message for a digit or a work noun -- both of which are just
# how a friend talks -- so her casual messages were getting a build-plan-sized
# reasoning budget. Hers relaxes to: short, and not an actual request to make
# something. False positives cost a short answer; false negatives cost a minute.
# ---------------------------------------------------------------------------
# the office-wide guards below exercise the non-Taliyah branch, which needs
# _QUICK_WORK_RE from further up main.py
s0 = src.index("_QUICK_WORK_RE = re.compile(")
s3 = src.index("_TALIYAH_WORK_RE = re.compile(")
e3 = src.index("def _fix_ask(message: str) -> bool:", s3)
ns3 = dict(ns)
ns3["TALIYAH_ID"] = "taliyah"
exec(src[s0:s3], ns3)
exec(src[s3:e3], ns3)
quick = ns3["_quick_reply_ask"]

QUICK_CASES = {
    # True -- cap her thinking, these want a person not an essay
    "rough day. the store did nothing again and i been at it since 6": True,
    "why you talking like that": True,
    "you up": True,
    "cant sleep": True,
    "i been at it since 6 this morning": True,
    "how much sleep you think i need": True,
    "be honest, do i sound stressed": True,
    # False -- she is being asked to produce something, let her think
    "write me a caption for this": False,
    "make me a picture of the mountains at night": False,
    "research that for me and tell me what you find": False,
    ("i want to talk through the whole thing with you, everything that happened this week "
     "with the store and the ads and my brother and i dont even know where to start with "
     "any of it honestly"): False,   # too long for a quick cap
}
qbad = [(m, w, quick(m, "taliyah")) for m, w in QUICK_CASES.items() if quick(m, "taliyah") != w]
if qbad:
    for m, w, got in qbad:
        print(f"FAIL [quick] {m[:50]!r}: want {w} got {got}")
    raise SystemExit(1)
# and the office-wide behaviour must be untouched for everyone else
assert quick("hows the systems?", "engineer") is False
assert quick("cool, ill grab some row cover", "engineer") is True
assert quick("the store did nothing again", "engineer") is False, "work nouns still count for work seats"
print(f"taliyah quick-cap battery: ALL PASS ({len(QUICK_CASES)} cases + 3 office-wide guards)")
