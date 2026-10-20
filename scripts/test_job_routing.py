"""Parity battery for jobs.py (Phase 1, PLAN-brain-graph.md).

Proves jobs.route() returns byte-identical booleans to the inline regexes
it replaced in main.py (2026-08-24), on Barry's real phrasings including
every measured ghost. Run from repo root:
    venv/Scripts/python.exe scripts/test_job_routing.py
Re-run this ANY time a detection regex in jobs.py changes.
"""
import re
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import jobs  # noqa: E402

MOVIE_ID = "movie"

# --- The OLD inline logic, copied exactly as it stood in main.py ---
def old_mega_write(agent_id, message):
    return agent_id == MOVIE_ID and re.search(
        r"\b(entire|whole|full|complete)\b.{0,40}\b(rewrite|script|"
        r"episode|production)\b|\brewrite\b.{0,30}\b(entire|whole|"
        r"all of it)\b", message, re.IGNORECASE | re.DOTALL) is not None

def old_names_a_shot(message):
    return re.search(
        r"\b(?:shots?|b-?rolls?|scenes?)\s*#?\s*"
        r"(?:[a-z]?\d+[a-z]?|\b[a-h]\b)",
        message, re.IGNORECASE) is not None

def old_shot_ask(agent_id, message, mega):
    return (agent_id == MOVIE_ID and not mega
            and (old_names_a_shot(message)
                 or (re.search(r"\bshots?\b|\bb-?rolls?\b", message,
                               re.IGNORECASE) is not None
                     and re.search(r"\bprompts?\b|\bseedance\b|\bhiggsfield\b"
                                   r"|\bgive\b|\bwrite\b|\bdirect\w*\b",
                                   message, re.IGNORECASE) is not None)
                 or re.search(r"\bprompts?\b", message, re.IGNORECASE)
                 is not None and re.search(
                     r"\bgenerat\w*\b|\bseedance\b|\bhiggsfield\b",
                     message, re.IGNORECASE) is not None))

# Real phrasings: every measured ghost + everyday asks + non-movie seats.
BATTERY = [
    ("movie", "Shots 2 and 3, please"),                     # THE ghost
    ("movie", "shot 14"),
    ("movie", "give me shots 2 and 3 for seedance 2.5"),
    ("movie", "write me a higgsfield prompt for the opening run"),
    ("movie", "write me the prompt for the opening run"),
    ("movie", "I want an entire rewrite of V8 in full production mode with seedance prompts"),
    ("movie", "rewrite the whole thing"),
    ("movie", "i want V8 written as a production script"),
    ("movie", "how many times does bia fire in act two?"),
    ("movie", "what happens in shot 4"),
    ("movie", "b-roll 01 please"),
    ("movie", "scene D"),
    ("movie", "why does keth trust b dubb?"),
    ("movie", "good morning man"),
    ("movie", "lets brainstorm episode 2 ideas"),
    ("movie", "redo it"),
    ("movie", "generate the prompt for the ridge run"),
    ("movie", "full production pass, act two"),
    ("cio", "Shots 2 and 3, please"),                       # non-movie seat
    ("taliyah", "write me a prompt"),
    ("engineer", "rewrite the whole module"),
    ("movie", ""),                                          # empty message
]

# Deliberate divergences from the old inline logic -- (agent_id, message)
# -> expected NEW job name. Barry's rulings, not regressions.
INTENDED = {
    # 2026-08-24 "write should be to elliot": writ\w* is a generation word now.
    ("movie", "write me the prompt for the opening run"): "shot_prompt",
}

fails = 0
for agent_id, msg in BATTERY:
    if (agent_id, msg) in INTENDED:
        job = jobs.route(agent_id, msg, MOVIE_ID)
        want = INTENDED[(agent_id, msg)]
        ok = job.name == want
        if not ok:
            fails += 1
        print(f"{'OK  ' if ok else 'FAIL'} {agent_id:9} {job.name:13} "
              f"names={job.names_a_shot!s:5} (INTENDED: {want}) :: {msg[:60]!r}")
        continue
    job = jobs.route(agent_id, msg, MOVIE_ID)
    o_mega = old_mega_write(agent_id, msg)
    o_shot = old_shot_ask(agent_id, msg, o_mega)
    o_names = old_names_a_shot(msg) if agent_id == MOVIE_ID else False
    n_mega = job.name == "mega_write"
    n_shot = job.name == "shot_prompt"
    # names_a_shot only ever consumed behind a MOVIE_ID check in main.py,
    # so parity is required only for the movie seat.
    ok = (o_mega == n_mega and o_shot == n_shot
          and (agent_id != MOVIE_ID or o_names == job.names_a_shot))
    tag = "OK  " if ok else "FAIL"
    if not ok:
        fails += 1
    print(f"{tag} {agent_id:9} {job.name:13} names={job.names_a_shot!s:5} "
          f"(old: mega={o_mega} shot={o_shot} names={o_names}) :: {msg[:60]!r}")

print(f"\n{'PARITY: ALL PASS' if fails == 0 else f'PARITY: {fails} FAILURES'} "
      f"across {len(BATTERY)} cases")
sys.exit(1 if fails else 0)
