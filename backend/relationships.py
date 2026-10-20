"""EVOLVING RELATIONSHIPS -- closeness that actually moves.

Barry, 2026-08-29: "they have to evolve their lifes, their relationships and
all... they may fight who knows how they may evolve."

THE GAP THIS CLOSES. Each agent already keeps a written opinion of every
coworker (mind-about-<name>), but nothing tracked HOW CLOSE they are, so break
room partners were picked with random.sample() -- Sophie and Taliyah being
best friends changed nothing about who ended up in a room together. Social
structure could never form because the system had no memory of who spends time
with whom.

THE RESEARCH. AgentSociety (arXiv 2502.08691) models every bond as a typed
relationship with a strength 0-100 and has agents choose partners by type and
strength. Network-formation studies of LLM societies (PNAS Nexus 2025; arXiv
2607.01148) find that once link formation is allowed to be unequal, agent
groups spontaneously develop preferential attachment and homophily -- real
social structure, unscripted. That is the whole mechanism: let closeness be a
number that moves, and let it steer who talks to whom.

DESIGN CHOICES, and why:
- **No model call anywhere in this file.** Closeness moves on BEHAVIOUR --
  time spent together -- not on an LLM's opinion of how a chat went. That
  keeps it off the GPU entirely (it can run while a render owns the card) and
  keeps it honest: it measures what actually happened, not what a model
  guessed about it.
- **Diminishing returns.** Each shared scene moves closeness less as it gets
  higher, so nobody saturates at 100 in a week.
- **Drift.** Closeness decays slowly toward neutral when a pair stops talking.
  Friendships need maintaining. This is what lets people drift apart.
- **Nothing is seeded.** Everyone starts at the same neutral 50. Who ends up
  close is entirely a product of who actually spends time together, which is
  itself steered by closeness -- the feedback loop that produces cliques.
- **Numbers never reach the model.** Agents are told "you and Sophie have
  gotten close" in plain words, never "closeness 74". A number in a prompt
  invites a model to perform the number.
"""
import math
import time

import memory

NEUTRAL = 50.0
FLOOR, CEIL = 0.0, 100.0
# a shared scene moves this much at neutral, less as closeness gets extreme
STEP = 3.0
# closeness pulls back toward NEUTRAL by this fraction per day of silence
DRIFT_PER_DAY = 0.02


def _ensure() -> None:
    with memory.get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                agent      TEXT NOT NULL,
                other      TEXT NOT NULL,
                closeness  REAL NOT NULL DEFAULT 50.0,
                scenes     INTEGER NOT NULL DEFAULT 0,
                last_at    REAL,
                PRIMARY KEY (agent, other)
            )""")


def _row(conn, a: str, b: str):
    r = conn.execute(
        "SELECT closeness, scenes, last_at FROM relationships "
        "WHERE agent=? AND other=?", (a, b)).fetchone()
    if r:
        return float(r["closeness"]), int(r["scenes"]), r["last_at"]
    return NEUTRAL, 0, None


def _drifted(closeness: float, last_at) -> float:
    """Silence pulls a bond back toward neutral. Friendships need feeding."""
    if not last_at:
        return closeness
    days = max(0.0, (time.time() - float(last_at)) / 86400.0)
    if days <= 0:
        return closeness
    pull = 1.0 - math.exp(-DRIFT_PER_DAY * days)
    return closeness + (NEUTRAL - closeness) * pull


def closeness(a: str, b: str) -> float:
    """Current closeness of a toward b, drift applied. 0-100, neutral 50."""
    _ensure()
    with memory.get_db() as conn:
        c, _, last = _row(conn, a, b)
    return max(FLOOR, min(CEIL, _drifted(c, last)))


def record_scene(participants: list[str], weight: float = 1.0) -> None:
    """They spent time together. Move every pair in the scene closer.

    weight lets a long one-to-one DM count for more than being two of five
    voices in a group chat -- caller decides, this file does not judge.
    """
    _ensure()
    now = time.time()
    ids = [p for p in dict.fromkeys(participants) if p]
    if len(ids) < 2:
        return
    with memory.get_db() as conn:
        for a in ids:
            for b in ids:
                if a == b:
                    continue
                c, n, last = _row(conn, a, b)
                c = _drifted(c, last)
                # diminishing returns: the closer they already are, the less
                # one more evening moves it
                headroom = (CEIL - c) / (CEIL - NEUTRAL)
                c = min(CEIL, c + STEP * weight * max(0.15, headroom))
                conn.execute(
                    "INSERT INTO relationships (agent, other, closeness, "
                    "scenes, last_at) VALUES (?,?,?,?,?) "
                    "ON CONFLICT(agent, other) DO UPDATE SET "
                    "closeness=excluded.closeness, scenes=excluded.scenes, "
                    "last_at=excluded.last_at",
                    (a, b, c, n + 1, now))


def describe(agent: str, others: dict[str, str]) -> str:
    """Plain-words summary for the agent's PERSONAL prompt. Never numbers --
    a model handed '74' performs the 74. `others` maps agent_id -> first name.
    Returns '' when nothing has diverged from neutral yet, so a fresh office
    says nothing rather than inventing closeness that has not happened."""
    _ensure()
    close, distant = [], []
    for oid, name in others.items():
        if oid == agent:
            continue
        c = closeness(agent, oid)
        if c >= 68:
            close.append(name)
        elif c <= 34:
            distant.append(name)
    if not close and not distant:
        return ""
    bits = []
    if close:
        bits.append("You have gotten close to " + _join(close) +
                    " -- you seek them out, and it shows.")
    if distant:
        bits.append("You and " + _join(distant) + " have drifted; there is "
                    "distance there, whatever the reason.")
    return "\n## WHERE YOU STAND WITH PEOPLE\n" + " ".join(bits) + "\n"


def _join(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def snapshot() -> list[dict]:
    """Read-only view for Barry -- who is close to whom, right now."""
    _ensure()
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT agent, other, closeness, scenes, last_at "
            "FROM relationships ORDER BY closeness DESC").fetchall()
    return [{"agent": r["agent"], "other": r["other"],
             "closeness": round(_drifted(float(r["closeness"]), r["last_at"]), 1),
             "scenes": r["scenes"]} for r in rows]
