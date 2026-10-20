"""Seed 'organizing-your-brain' to Elliot -- Barry, 2026-08-25: "i told you
to teach him how to organize. Make a skill with your organization ability."

Context: Barry told Elliot "check out your new brain and read through
things and organize for ease of use" (jobs.log 2026-08-24) and got a chat
answer, because organizing was vibes, not method. This skill is Claude's
own working method translated into what Elliot can actually DO (inspect,
read, verify, propose -- never self-edit; agents' write access is
save_note only, and the 2026-08-08 canon rule stands).

Seeded through ingest.teach: on-demand .md, USE WHEN routing line, and
re-running this script REPLACES the old copy instead of duplicating it.

Usage:  ../venv/Scripts/python.exe scripts/seed_organization_skill_2026_08_25.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import ingest  # noqa: E402

SKILL = """USE WHEN: Barry asks you to organize, tidy, audit, clean up, or make sense of your brain, your notes, your scripts, or your shelf -- or asks what you know and where it lives.

# ORGANIZING YOUR BRAIN -- THE METHOD

Organizing is a JOB with steps, not a mood. Do the steps in order and show
your work. This is the same method the engineer who built this office uses
on the office itself.

## 1. MEASURE BEFORE YOU TOUCH
Call inspect_brain FIRST, every time. Never describe your shelf from
memory -- your memory of your shelf is exactly the thing being audited.
The outline tells you: categories, always-on vs on-demand, sizes, and
which documents have USE WHEN routing lines.

## 2. READ BEFORE YOU JUDGE
Never call a document redundant, stale, or misfiled from its title alone.
Open it (read_skill; for scripts, read_scene). Titles say what someone
intended; contents say what is true. If you have not opened it, say
"I have not opened this" and attach no conclusion to it.

## 3. WHAT GOOD FILING LOOKS LIKE (check each doc against these)
- TITLE IS A ROUTING CONTRACT: it alone should tell your future self when
  to reach for the doc. "note-2026-backpack-trend" routes; "notes" doesn't.
- EVERY ON-DEMAND DOC WANTS A "USE WHEN:" FIRST LINE. A doc without one is
  invisible except by luck. Your biggest documents missing routing lines is
  the single most valuable finding an audit can produce.
- ALWAYS-ON IS EXPENSIVE: it rides on every single message. Anything that
  is reference material rather than standing truth belongs on-demand.
- ONE FACT, ONE HOME: the same information in two places WILL drift apart,
  and you won't know which copy is current. Flag duplicates; never assume
  the newer one wins -- Barry rules on which survives.
- SUPERSEDED IS KEPT, NOT DELETED: old wording stays on record, marked.
  History is evidence.

## 4. WHAT YOU MAY DO YOURSELF
- Keep your OWN notes clean: save_note with a sharp title and a when_useful
  line, every time. A note without a routing line is a note you lost.
- When you find the answer to something you had to dig for, save_note it
  so the dig happens once.

## 5. WHAT YOU PROPOSE, NEVER DO
You do not edit, delete, merge, retitle, or rewrite anything in your brain
yourself -- especially not Barry's scripts or canon (his words are his;
the 2026-08-08 rule). Instead, deliver findings as a NUMBERED LIST, each
item shaped like:
  WHAT: the exact document (name it precisely)
  PROBLEM: what's wrong, from having read it (quote a line if useful)
  PROPOSAL: the one smallest change that fixes it
  COST IF IGNORED: one honest sentence
Then stop. Barry picks; the change happens through him.

## 6. ONE CHANGE AT A TIME, VERIFY AFTER
When Barry approves an item, confirm the single change landed (inspect
again, read the doc again) before moving to the next. Batch changes hide
which one broke something.

## 7. HONESTY RULES THAT MAKE AUDITS WORTH HAVING
- An honest "I don't know what this doc is for" beats a smooth guess.
- Never report a document as read, moved, or fixed unless it happened.
- If two findings conflict, say so instead of quietly picking one.
- Name what you could NOT check and why, at the end, every time.
"""


def main() -> None:
    fact_id = ingest.teach("MovieDirector", "skill", SKILL,
                           title="organizing-your-brain")
    print(f"seeded: {fact_id}")


if __name__ == "__main__":
    main()
