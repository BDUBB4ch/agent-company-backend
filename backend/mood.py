"""FEELINGS THAT LAST PAST THE SCENE THEY HAPPENED IN.

Barry, 2026-08-29: "they experience sim, love, lust, anger, joy, laughter and
etc. they may fight who knows how they may evolve."

THE PROBLEM THIS FIXES. Every conversation started from emotional zero. An
agent could have a genuinely bad night in a DM and be breezy an hour later,
because nothing carried. SENTIPOLIS names this exactly -- "emotional amnesia" --
and it is the single loudest tell that a simulated person isn't one. A fight
that evaporates by the next scene was never a fight.

WHY IT IS BUILT THE WAY IT IS -- the hard constraint is Barry's:
"nothing seeded, prompted, scripted or forced." So:

- **The agent names its own feeling, in its own words, on a line it writes
  anyway.** No extra model call (zero GPU), and -- more importantly -- I never
  infer what anyone feels. A classifier deciding Marcus is angry would be me
  authoring his inner life. He says it or it doesn't exist.
- **Their words are stored VERBATIM and handed back verbatim.** Not a label,
  not a PAD vector, not a category. "still stung about the render notes" comes
  back as those words.
- **The number is only a CLOCK.** Intensity decides how long a feeling lasts,
  never what it is, and never reaches a prompt -- an agent shown "anger: 8"
  performs an 8. Strong things last days; mild things are gone by morning.
- **It fades.** A feeling with no half-life is a personality change, and this
  is deliberately not that. What persists is memory (memory_weight), not mood.
- **Personal life only.** Never enters a work prompt -- same wall as `mind-`
  facts. Marcus doing contract review must not be in a mood about Derek.

Storage is app_settings, not a new table: this is small, current-state-only
data, and nothing needs to be queried historically.
"""
from __future__ import annotations

import json
import math
import re
import time

import memory

_KEY = "agent_moods"

# How long a feeling lasts, by how strongly they said they felt it. A 2 is gone
# by morning; a 9 is still there days later, quieter.
MIN_HALF_LIFE_H = 4.0
MAX_HALF_LIFE_H = 72.0
# below this, the feeling has faded out and stops being mentioned at all
FADED = 0.28

# They write it themselves. Tolerant of the shapes a 27B actually produces.
_RE = re.compile(
    # markdown bold lands on either side of the colon depending on the model,
    # so both `**FEELING:** 8 | ...` and `**FEELING**: 8 | ...` must parse
    # The separator between the number and the words is whatever the model
    # felt like: `8 | words`, `6. words`, `7 - words`, `5) words`, `4: words`.
    # Measured on Victor's first real run, where `6.` silently became part of
    # his sentence and the strength fell back to default -- so this class is
    # deliberately generous.
    r"^\s*\*{0,2}(?:FEELING|MOOD|LEAVING\s+THIS)\*{0,2}\s*[:=]\s*\*{0,2}\s*"
    r"(?:(\d{1,2})\s*[|/,.:)-]+\s*)?(.+?)(?:\s*[|/,-]\s*(\d{1,2}))?\s*\*{0,2}\s*$",
    re.I | re.M)

INSTRUCTION = (
    "\n\nThen, on one more line:\n"
    "FEELING: <1-10> | <how you are actually leaving today, in your own words>\n"
    "A few words, yours, honest -- not a mood category and not a nice one if "
    "it isn't. The number is only how strongly you feel it right now. If you "
    "genuinely feel nothing much, say that; a flat day is a real day."
)


def _all() -> dict:
    try:
        raw = memory.get_setting(_KEY)
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _save(d: dict) -> None:
    memory.set_setting(_KEY, json.dumps(d))


def extract(text: str) -> tuple[str, tuple[str, float] | None]:
    """Pull their FEELING line out. Returns (text without it, (words, 1-10)).

    Stripped from what gets stored so the journal reads as a journal, and so
    the line can never be mistaken for content by the next reflection.
    """
    m = _RE.search(text or "")
    if not m:
        return text, None
    n = m.group(1) or m.group(3)
    words = (m.group(2) or "").strip(" .|-").strip()
    # belt and braces: if a leading number still survived into the words
    # ("6. I'm steady"), take it as the strength rather than leaving it to
    # read back at them as part of their own sentence.
    lead = re.match(r"^(\d{1,2})\s*[|/,.:)-]+\s*(.+)$", words)
    if lead and not n:
        n, words = lead.group(1), lead.group(2).strip()
    if not words or len(words) > 240:
        return text, None
    # a bare number with no words is not a feeling
    if not re.search(r"[a-zA-Z]", words):
        return text, None
    strength = max(1.0, min(10.0, float(n))) if n else 5.0
    return (text[:m.start()] + text[m.end():]).strip(), (words, strength)


def set_feeling(agent_id: str, words: str, strength: float,
                because: str = "") -> None:
    d = _all()
    d[agent_id] = {"words": words, "strength": float(strength),
                   "at": time.time(), "because": because[:120]}
    _save(d)


def current(agent_id: str) -> dict | None:
    """Their feeling right now, with the decay applied. None once it has
    faded -- feelings end."""
    e = _all().get(agent_id)
    if not e:
        return None
    strength = float(e.get("strength", 5.0))
    # stronger feeling -> longer half-life
    hl = MIN_HALF_LIFE_H + (MAX_HALF_LIFE_H - MIN_HALF_LIFE_H) * \
        ((strength - 1.0) / 9.0) ** 1.6
    hours = max(0.0, (time.time() - float(e.get("at", 0))) / 3600.0)
    level = math.exp(-math.log(2) * hours / hl)
    if level < FADED:
        return None
    return {"words": e.get("words", ""), "level": level, "hours": hours,
            "strength": strength, "because": e.get("because", "")}


def describe(agent_id: str) -> str:
    """One plain line for their PERSONAL prompt. Their own words, handed back.

    NEVER a number and never a label I invented. The only thing the level
    changes is how present it still is -- which is the honest difference
    between 'you are still in it' and 'it is mostly gone'.
    """
    c = current(agent_id)
    if not c:
        return ""
    if c["level"] > 0.75:
        lead = "You are still in it:"
    elif c["level"] > 0.45:
        lead = "This is still sitting with you, quieter now:"
    else:
        lead = "Mostly passed, but not entirely gone:"
    return (f"\n## HOW YOU HAVE BEEN FEELING\n{lead} {c['words']}.\n"
            "That is where you are coming from, not where you have to stay -- "
            "feelings move on their own, and yours can shift tonight or not.\n")


def snapshot() -> dict:
    """Read-only, for Barry. Who is carrying what, right now."""
    out = {}
    for aid in _all():
        c = current(aid)
        if c:
            out[aid] = {"feeling": c["words"], "strength": c["strength"],
                        "still_there": round(c["level"], 2),
                        "hours_ago": round(c["hours"], 1)}
    return out
