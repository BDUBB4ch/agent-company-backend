"""Job routing -- Phase 1 of the brain graph plan (PLAN-brain-graph.md).

THE JOB PICKS THE REGION. Each agent has a handful of named jobs; each job
maps to a context region (what gets injected/rebuilt for that kind of ask).
This module is the single source of truth for DETECTION: which job a
message is. The regexes here were moved VERBATIM from main.py's scattered
Elliot branches (2026-08-24) -- behavior is intended to be byte-identical
to the old inline booleans. The injection/assembly code itself still lives
in main.py for now; consolidating it into region specs is the next step.

Why a table instead of inline booleans: the _shot_ask ghost. "Shots 2 and
3, please" carried no verb from the old trigger list, so the entire
shot-ask apparatus silently never fired and it read for WEEKS as Elliot
ignoring instructions. A misroute must be visible, not silent -- so every
route is logged (console + data/jobs.log), and there is ALWAYS a default
job ("chat"), never "no region".

ELLIOT'S JOB TABLE (priority order -- first match wins):
  factual_script  what a scene/script says, verbatim -- served straight
                  from the DB by main._script_verbatim_reply, NO model
                  call. Detected by that function (needs the script index),
                  so it logs its own [job] line at the gate; it runs before
                  route() is ever reached.
  mega_write      entire/whole/full rewrite passes -- task-scoped system
                  prompt (persona + anchors + act chunk + ledger + format
                  contract), recall OFF, pass-1 nudge in the user turn.
  shot_prompt     a named shot / prompt-writing ask -- craft-stripped
                  block + exemplars injected, two-stage directive,
                  recall OFF when a shot is actually named.
  chat            everything else -- pins + brain + recall, untouched.

All other agents: always "chat" (their job tables come after Elliot's
side is measured -- one agent at a time, per the plan's guardrails).
"""

import os
import re
from dataclasses import dataclass
from datetime import datetime

from config import DATA_DIR

JOBS_LOG_PATH = os.path.join(DATA_DIR, "jobs.log")

# --- Detection regexes, moved verbatim from main.py (2026-08-24). ---
# Do not "improve" these here without re-running the parity battery in
# scripts/test_job_routing.py -- every pattern below carries a measured
# lesson (see main.py's comment history for each).

# Mega-write: "entire rewrite of V8 in full production mode" etc.
_MEGA_WRITE_RE = re.compile(
    r"\b(entire|whole|full|complete)\b.{0,40}\b(rewrite|script|"
    r"episode|production)\b|\brewrite\b.{0,30}\b(entire|whole|"
    r"all of it)\b", re.IGNORECASE | re.DOTALL)

# Naming a numbered shot/b-roll/scene is sufficient on its own
# (2026-08-23 -- the verb requirement only ever produced false negatives).
_NAMES_A_SHOT_RE = re.compile(
    r"\b(?:shots?|b-?rolls?|scenes?)\s*#?\s*"
    r"(?:[a-z]?\d+[a-z]?|\b[a-h]\b)", re.IGNORECASE)

# Unnumbered shot-ask shapes (shot-word + verb, or prompt + generation).
_SHOT_WORD_RE = re.compile(r"\bshots?\b|\bb-?rolls?\b", re.IGNORECASE)
_SHOT_VERB_RE = re.compile(
    r"\bprompts?\b|\bseedance\b|\bhiggsfield\b"
    r"|\bgive\b|\bwrite\b|\bdirect\w*\b", re.IGNORECASE)
_PROMPT_RE = re.compile(r"\bprompts?\b", re.IGNORECASE)
# "writ\w*" added 2026-08-24 (Barry: "write should be to elliot") -- fixes
# the latent miss the parity battery surfaced: "write me the prompt for the
# opening run" carried no generation word and fell through to plain chat.
_GENERATION_RE = re.compile(
    r"\bgenerat\w*\b|\bseedance\b|\bhiggsfield\b|\bwrit\w*\b", re.IGNORECASE)


@dataclass
class Job:
    name: str            # "mega_write" | "shot_prompt" | "chat"
    names_a_shot: bool   # separate signal: gates recall + block lookup
    trigger: str         # human-readable why, for the log line


# Token for one shot reference: "12", "C5", "4b", or a bare section letter.
# The bare letter refuses a following hyphen -- otherwise "and b-roll 2" in
# a tail reads the "b" of "b-roll" as SCENE B (the same disease as the old
# "SHOT D invented out of 'and'" ghost, one connector further along).
_SHOT_TOK = r"(?:[a-z]?\d+[a-z]?|[a-h]\b(?!-))"
_SHOT_LIST_RE = re.compile(
    r"\b(shot|b-?roll|scene)s?\s*#?\s*(" + _SHOT_TOK + r")"
    r"((?:\s*(?:,|and|&|through|thru|to|-)\s*#?\s*" + _SHOT_TOK + r")*)",
    re.IGNORECASE)
_SHOT_TAIL_RE = re.compile(
    r"\s*(,|and|&|through|thru|to|-)\s*#?\s*(" + _SHOT_TOK + r")",
    re.IGNORECASE)


def parse_shot_list(message: str) -> list[tuple[str, str]]:
    """Every (KIND, NUMBER) shot reference in Barry's message, in order.

    Moved out of main.py's chat handler 2026-08-25 so it is TESTABLE -- this
    exact path produced silent bugs in two separate sessions ("Shots 2 and
    3" dropping the 3; "shots 4-6" dropping the 5) and both survived weeks
    because nothing could exercise the logic without a live chat call.

    The tail is walked as (connector, token) PAIRS rather than stripping
    connectors first: the 2026-08-23 fix threw the connectors away, which
    flattened every RANGE to its endpoints -- "shots 4-6" became [4, 6] and
    shot 5 was silently never fetched (Barry, 2026-08-25: "you skipped
    shot5"). "-", "to", "through", "thru" between two plain numbers expand
    inclusively (span capped at 8); "and", "," and "&" remain lists, so
    "Shots 2 and 3" is unchanged.
    """
    wanted: list[tuple[str, str]] = []
    for m in _SHOT_LIST_RE.finditer(message):
        kind = m.group(1).upper().replace("BROLL", "B-ROLL")
        nums = [m.group(2)]
        for cm in _SHOT_TAIL_RE.finditer(m.group(3) or ""):
            conn, cur = cm.group(1).lower(), cm.group(2)
            prev = nums[-1]
            if (conn in ("-", "to", "through", "thru")
                    and prev.isdigit() and cur.isdigit()
                    and 0 < int(cur) - int(prev) <= 8):
                nums += [str(k) for k in range(int(prev) + 1, int(cur) + 1)]
            else:
                nums.append(cur)
        for n in nums:
            wanted.append((kind, n.upper()))
    return wanted


def route(agent_id: str, message: str, movie_id: str) -> Job:
    """Name the job this message is. Never raises; the default is always
    Job("chat", ...) -- a routing failure must degrade to the normal path,
    never to a missing region."""
    try:
        if agent_id != movie_id:
            return Job("chat", False, "default (no job table for this seat yet)")
        msg = message or ""
        names_a_shot = _NAMES_A_SHOT_RE.search(msg) is not None
        if _MEGA_WRITE_RE.search(msg):
            return Job("mega_write", names_a_shot, "entire/whole-rewrite shape")
        if names_a_shot:
            return Job("shot_prompt", True, "names a numbered shot/b-roll/scene")
        if _SHOT_WORD_RE.search(msg) and _SHOT_VERB_RE.search(msg):
            return Job("shot_prompt", False, "shot-word + verb")
        if _PROMPT_RE.search(msg) and _GENERATION_RE.search(msg):
            return Job("shot_prompt", False, "prompt + generation word")
        return Job("chat", names_a_shot, "default")
    except Exception as exc:  # pragma: no cover -- belt and braces
        return Job("chat", False, f"route() failed ({exc}); defaulted")


def log(office_name: str, job_name: str, trigger: str, message: str) -> None:
    """One line per routed message -- console AND data/jobs.log, so a
    misroute is diagnosable without access to the backend console window
    (processes started by the watchdog print somewhere nobody reads).
    Best-effort: logging must never cost a turn."""
    line = (f"{datetime.now().isoformat(timespec='seconds')} "
            f"{office_name}: {job_name} ({trigger}) :: {message[:100]!r}")
    print(f"[job] {line}")
    try:
        with open(JOBS_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass
