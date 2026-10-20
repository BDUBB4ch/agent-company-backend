"""MEMORY THAT EVOLVES -- importance, and a forgetting curve.

Barry, 2026-08-29: "their minds have to evolve based on experiences, like real
people."

THE PROBLEM THIS FIXES. Every mind- fact weighed exactly the same, and
consolidation (reflect._inner_life) simply took the six most RECENT. So a
stray thought from an hour ago outranked the night something actually
happened, and nothing ever faded. That is not a mind evolving -- it is a mind
accumulating flatly, with a six-item window sliding over it.

THE RESEARCH. Park et al. (arXiv 2304.03442) score retrieval on
importance x recency x relevance, and have the agent rate the importance of
its own memory as it is written. MemoryBank adds an Ebbinghaus forgetting
curve so memory strength decays with time and high-value experience survives
while trivia sinks. This module is those two ideas, kept small.

DESIGN CHOICES:
- **The agent rates its own memory**, on one line it writes anyway. No extra
  model call, so no extra GPU. Park's method exactly.
- **Nothing is ever deleted.** Importance changes what gets RECALLED, not what
  exists. A faded memory is still there and can resurface if it matters again.
- **The number never goes back into a prompt.** An agent shown "importance 8"
  performs the 8. It only ever sorts.
- **Missing weight is not a failure.** Anything unrated sits at NEUTRAL, so
  every memory written before today still works and nothing needs migrating.
"""
import math
import re
import time

import memory

NEUTRAL = 5.0
MIN_W, MAX_W = 1.0, 10.0
# half-life in days for the recency half of the score. ~2 weeks: last night
# clearly beats last month, but a big memory from three weeks ago can still
# outrank a trivial one from yesterday -- which is the whole point.
HALF_LIFE_DAYS = 14.0

# The agent writes this line itself, at the end of its journal.
_WEIGHT_RE = re.compile(
    # markdown bold on either side of the colon (`**WEIGHT:** 8`, `**WEIGHT**: 8`)
    # -- the bare form let "**WEIGHT:** 8" ride into three personality files
    # as if it were a sentence about themselves (found 2026-09-10).
    r"^\s*\*{0,2}(?:WEIGHT|IMPORTANCE)\*{0,2}\s*[:=]\s*\*{0,2}\s*(\d{1,2})\s*(?:/\s*10)?\s*\*{0,2}\s*$",
    re.I | re.M)

# One paragraph appended to the reflection prompt. Deliberately framed as
# "how much did this matter to YOU" -- a judgement only they can make -- and
# NOT as "rate this for the system", which invites performing a number.
WEIGHT_INSTRUCTION = (
    "\n\nAt the very end, on its own last line, write:\n"
    "WEIGHT: <1-10>\n"
    "That is your own honest sense of how much today actually mattered to "
    "you -- 1 for a quiet nothing day, 10 for something you will still be "
    "carrying months from now. It is not a score of how well you wrote and "
    "nobody is grading it. It decides what stays with you and what fades, so "
    "answer it the way you actually feel it."
)


def ensure_column() -> None:
    """Add the importance column if it isn't there. Same try/except ALTER
    pattern this codebase already uses for schema growth."""
    with memory.get_db() as conn:
        try:
            conn.execute("ALTER TABLE facts ADD COLUMN importance REAL")
        except Exception:
            pass  # already present


def extract(body: str) -> tuple[str, float | None]:
    """Pull the agent's own WEIGHT line out of a journal section.

    Returns (body without the line, weight) -- the line is stripped so it
    never shows up in what Barry reads or in what rides back into the next
    reflection.
    """
    m = _WEIGHT_RE.search(body or "")
    if not m:
        return body, None
    w = max(MIN_W, min(MAX_W, float(m.group(1))))
    return (body[:m.start()] + body[m.end():]).strip(), w


def set_weight(fact_id: int, weight: float | None) -> None:
    if weight is None:
        return
    ensure_column()
    with memory.get_db() as conn:
        conn.execute("UPDATE facts SET importance=? WHERE id=?",
                     (float(weight), fact_id))


def _age_days(created) -> float:
    if not created:
        return 0.0
    try:
        if isinstance(created, (int, float)):
            return max(0.0, (time.time() - float(created)) / 86400.0)
        import datetime
        dt = datetime.datetime.fromisoformat(str(created)[:19])
        return max(0.0, (datetime.datetime.now() - dt).total_seconds() / 86400.0)
    except Exception:
        return 0.0


def score(importance, created) -> float:
    """importance x recency-decay. The Ebbinghaus half of MemoryBank."""
    w = float(importance) if importance is not None else NEUTRAL
    decay = math.exp(-math.log(2) * _age_days(created) / HALF_LIFE_DAYS)
    # floor the decay so an old but heavy memory never drops to nothing --
    # people do keep the big things.
    return w * max(0.15, decay)


def top_memories(office: str, limit: int = 6) -> list[dict]:
    """The agent's own thoughts, ranked by what actually mattered rather than
    by what happened last. This is what makes consolidation evolve."""
    ensure_column()
    category = f"private:{office}"
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT id, source_name, content, importance, created_at "
            "FROM facts WHERE category=? AND status='active' "
            "AND source_name LIKE 'mind-%' "
            "ORDER BY id DESC LIMIT 60", (category,)).fetchall()
    ranked = sorted(
        ({"id": r["id"], "source_name": r["source_name"],
          "content": r["content"], "importance": r["importance"],
          "created_at": r["created_at"],
          "_s": score(r["importance"], r["created_at"])} for r in rows),
        key=lambda d: -d["_s"])
    return ranked[:limit]


def stats(office: str) -> dict:
    ensure_column()
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT importance FROM facts WHERE category=? AND status='active' "
            "AND source_name LIKE 'mind-%'", (f"private:{office}",)).fetchall()
    rated = [r["importance"] for r in rows if r["importance"] is not None]
    return {"memories": len(rows), "rated": len(rated),
            "avg_weight": round(sum(rated) / len(rated), 1) if rated else None}
