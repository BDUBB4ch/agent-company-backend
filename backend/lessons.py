"""THEY LEARN -- the lessons ledger (2026-09-10).

Barry: "they also need to learn. however that is done by models such as
yourself, i want them to have that ability."

How Claude learns in this office is not weights: it is a small set of memory
files -- each one fact, with WHY it matters and HOW to apply it -- indexed and
loaded into context every session. This is that, per agent:

  * `remember_lesson` (tool, all nine) -- the agent writes a lesson in its own
    words: what it learned, why, how to apply it next time. The reflection
    door WHAT I LEARNED lands here too.
  * The ledger is ONE always-on fact per agent (`my-lessons`, no .md), so the
    lessons are in front of them on EVERY message -- the difference between
    this and save_note, which is on-demand and fires at the measured ~1%
    read_skill rate. Capped hard (LEDGER_CAP) because always-on is expensive;
    the newest lessons survive.
  * Near-duplicates REFRESH instead of stacking (difflib ratio) -- the
    personality file showed what unguarded appends do: the same sentence three
    nights running.
  * Nothing is planted: the ledger is empty until they write into it.

Records live in data/lessons/<office>.json; the fact is regenerated from them
so it can never drift from the record (the team-loops pattern).
"""
from __future__ import annotations

import datetime
import difflib
import json
import os
import re

import memory

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
LESSONS_DIR = os.path.join(_ROOT, "data", "lessons")
LEDGER_SOURCE = "my-lessons"      # no .md -> ALWAYS-ON, deliberately
LEDGER_CAP = 3500                 # chars of prompt on every message -- keep it small
MAX_LESSON = 360
MAX_WHY = 240
MAX_HOW = 240
SIMILAR = 0.82


def _path(office: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", office)
    return os.path.join(LESSONS_DIR, f"{safe}.json")


def load(office: str) -> list[dict]:
    try:
        with open(_path(office), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save(office: str, items: list[dict]) -> None:
    os.makedirs(LESSONS_DIR, exist_ok=True)
    tmp = _path(office) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, _path(office))


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (s or "").lower()).strip()


# ---- THE LEARNING LOOP (2026-09-24, Barry: "build the learning system") --------------------------
# Each lesson now carries WHERE it came from and whether real outcomes backed it:
#   source   "barry"    -- Barry told them (never auto-archived, kept first under the cap)
#            "verified" -- written citing a real outcome event (outcomes.py id)
#            "self"     -- their own view, no outside evidence
#   evidence outcome ids; helpful / harmful: times a later outcome CONFIRMED or CONTRADICTED it
#   archived lessons stay in the record, off the always-on ledger.
# The counts never reach a prompt (living-minds rule: numbers stay out). The agent writes and judges
# every lesson itself; code only keeps score and archives what kept failing.
ARCHIVE_WHEN_HARMFUL_BY = 2      # harmful >= helpful + 2  -> archived (not Barry's)
SELF_STALE_DAYS = 60             # a self-only lesson never confirmed in 60 days -> archived
PROMOTE_AT = 3                   # confirmed 3 times -> offered as a permanent skill (save_note)
_RANK = {"barry": 0, "verified": 1, "self": 2}


def active(items: list[dict]) -> list[dict]:
    return [it for it in items if not it.get("archived")]


def _render(items: list[dict], first_name: str) -> str:
    lines = [f"WHAT {first_name.upper()} HAS LEARNED (their own lessons, in their words -- "
             f"apply them; the number is how to refer to one in a learning review)"]
    for n, it in enumerate(items, 1):
        tag = " (from Barry)" if it.get("source") == "barry" else ""
        line = f"{n}. [{it.get('date','')}]{tag} {it.get('lesson','').strip()}"
        if it.get("why"):
            line += f" WHY: {it['why'].strip()}"
        if it.get("how"):
            line += f" HOW: {it['how'].strip()}"
        lines.append(line)
    return "\n".join(lines)


def prune(items: list[dict]) -> list[str]:
    """Archive what real outcomes kept contradicting, and self-only lessons nothing ever confirmed.
    Returns the archived lesson texts (for the log). Barry's lessons are never auto-archived."""
    out, today = [], datetime.date.today()
    for it in items:
        if it.get("archived") or it.get("source") == "barry":
            continue
        h, b = int(it.get("helpful", 0)), int(it.get("harmful", 0))
        last = it.get("last_confirmed") or it.get("date") or today.isoformat()
        try:
            age = (today - datetime.date.fromisoformat(last[:10])).days
        except ValueError:
            age = 0
        if b >= h + ARCHIVE_WHEN_HARMFUL_BY or (it.get("source", "self") == "self" and h == 0
                                                 and age > SELF_STALE_DAYS):
            it["archived"] = today.isoformat()
            out.append(it.get("lesson", ""))
    return out


def ready_to_promote(office: str) -> list[tuple[int, dict]]:
    """Lessons confirmed PROMOTE_AT+ times and not yet offered as a skill: (ledger number, item)."""
    return [(n, it) for n, it in enumerate(active(load(office)), 1)
            if int(it.get("helpful", 0)) >= PROMOTE_AT and not it.get("promoted")]


def refresh_ledger(office: str, first_name: str) -> str:
    """Regenerate the always-on fact from the record. Empty record = no fact
    (an empty ledger must not cost a byte of prompt)."""
    items = active(load(office))
    cat = f"private:{office}"
    with memory.get_db() as conn:
        conn.execute("UPDATE facts SET status='superseded' WHERE category=? AND "
                     "source_name=? AND status='active'", (cat, LEDGER_SOURCE))
    if not items:
        return ""
    # Over the cap, drop the LEAST backed first: oldest self-only, then oldest verified; Barry's last.
    text = _render(items, first_name)
    while len(text) > LEDGER_CAP and len(items) > 1:
        drop = min(range(len(items)), key=lambda i: (-_RANK.get(items[i].get("source", "self"), 2), i))
        items = items[:drop] + items[drop + 1:]
        text = _render(items, first_name)
    memory.add_fact(category=cat, content=text, source_name=LEDGER_SOURCE,
                    title=f"What {first_name} has learned")
    return text


def judge(office: str, first_name: str, number: int, verdict: str, evidence=None) -> dict:
    """The AGENT's own call on an existing lesson (ledger number) after a real outcome:
    'confirmed' (it held) or 'contradicted' (it failed / was wrong)."""
    import outcomes
    items = load(office)
    act = active(items)
    if not 1 <= int(number) <= len(act):
        return {"saved": False, "error": f"There is no lesson #{number} on your ledger (1-{len(act)})."}
    it = act[int(number) - 1]
    ev = sorted(outcomes.exists(office, evidence or []))
    v = (verdict or "").lower()
    if v not in ("confirmed", "contradicted"):
        return {"saved": False, "error": "verdict must be 'confirmed' or 'contradicted'."}
    if v == "confirmed":
        it["helpful"] = int(it.get("helpful", 0)) + 1
        it["last_confirmed"] = datetime.date.today().isoformat()
    else:
        it["harmful"] = int(it.get("harmful", 0)) + 1
    it["evidence"] = sorted(set(it.get("evidence", [])) | set(ev))
    gone = prune(items)
    _save(office, items)
    refresh_ledger(office, first_name)
    msg = f"Lesson #{number} marked {v}."
    if gone:
        msg += " It has now failed often enough that it came off your ledger (kept in your record)."
    return {"saved": True, "result": msg}


def remember(office: str, first_name: str, lesson: str, why: str = "",
             how: str = "", evidence=None, from_barry: bool = False) -> dict:
    import outcomes
    ev = sorted(outcomes.exists(office, evidence or []))
    source = "barry" if from_barry else ("verified" if ev else "self")
    lesson = " ".join((lesson or "").split())[:MAX_LESSON]
    why = " ".join((why or "").split())[:MAX_WHY]
    how = " ".join((how or "").split())[:MAX_HOW]
    if len(lesson) < 12:
        return {"saved": False, "error": "A lesson needs a real sentence -- what you learned."}
    items = load(office)
    today = datetime.date.today().isoformat()
    key = _norm(lesson)
    for it in items:
        if difflib.SequenceMatcher(None, key, _norm(it.get("lesson", ""))).ratio() >= SIMILAR:
            # the same lesson learned again: refresh, don't stack
            it.update({"date": today, "lesson": lesson,
                       "why": why or it.get("why", ""), "how": how or it.get("how", "")})
            it["times"] = int(it.get("times", 1)) + 1
            it["archived"] = None                       # learned again -> back on the ledger
            if _RANK.get(source, 2) < _RANK.get(it.get("source", "self"), 2):
                it["source"] = source                  # upgrade self -> verified -> barry, never down
            it["evidence"] = sorted(set(it.get("evidence", [])) | set(ev))
            _save(office, items)
            refresh_ledger(office, first_name)
            return {"saved": True, "refreshed": True, "count": len(items),
                    "result": "You already had this one -- refreshed it with today's wording."}
    items.append({"date": today, "lesson": lesson, "why": why, "how": how, "times": 1,
                  "source": source, "evidence": ev, "helpful": 0, "harmful": 0})
    _save(office, items)
    text = refresh_ledger(office, first_name)
    kept = len(re.findall(r"\n\d+\. ", text))
    return {"saved": True, "count": len(items), "kept_always_on": kept,
            "result": (f"Kept. It is now part of what you carry into every "
                       f"conversation ({kept} lessons on the ledger).")}


def forget(office: str, first_name: str, index: int) -> bool:
    items = load(office)
    if 0 <= index < len(items):
        items.pop(index)
        _save(office, items)
        refresh_ledger(office, first_name)
        return True
    return False
