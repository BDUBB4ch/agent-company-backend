"""Seed the one fact that teaches every agent how their own brain is filed.

Owner's instruction 2026-08-07: "they need to know how to categorize their info."

Idempotent: supersedes any previous copy before inserting.
Run: ../venv/Scripts/python.exe scripts/seed_filing_rules.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import memory  # noqa: E402

SRC = "how-your-brain-is-filed"

TITLE = "HOW YOUR BRAIN IS FILED -- read this before you store anything"

BODY = """Your memory is not one pile. It has categories and two speeds, and filing
something in the wrong place either buries it or bloats every message you send.

TWO SPEEDS -- this is the single most important thing:
- ALWAYS-ON: rides along on EVERY message you ever send. Use for short, durable
  facts you need constantly. Keep these tight.
- ON-DEMAND: only the TITLE appears in your skills index; you pull the body in
  yourself with the read_skill tool when a job actually touches it.
- WHICH ONE YOU GET IS DECIDED BY THE SOURCE NAME: if it ends in .md it is
  ON-DEMAND. Anything else is ALWAYS-ON. So a long document belongs in a .md
  source name, and a one-line fact does not.
- Rule of thumb: if it is longer than a short paragraph, or you would only need
  it for one kind of job, it belongs ON-DEMAND.

CATEGORIES -- where things go:
- owner              Who Barry is and what he is working toward. Everyone sees it.
- business:bdubbgrows   B Dubb Grows LLC -- the gardening/hydroponic supply store.
- business:gotchoback   Gotcho Back -- the backpack brand.
- business:pid          PID / piddevice.com. NEVER mix PID with the other two.
- domain:<name>      Reusable reference know-how (legal, marketing, business_ops,
                     engineering, horticulture). Granted per agent.
- knowledge:<name>   Shared canon everyone works from (product catalog, talia_crew
                     character canon, image prompting, email marketing, revenue).
- private:<you>      Yours alone. Notes, uploads dropped on your panel, your
                     PRIORITY and LESSON entries from Barry's approvals.

HOW TO WRITE A NEW ENTRY:
1. TITLE FIRST, in capitals, on its own line. Short and specific -- it is how you
   and everyone else find it later. "B DUBB GROWS -- EMAIL PLATFORMS", not "notes".
2. Then the body. Lead with the rule or the number, not the backstory.
3. Say WHEN it was decided and WHO decided it if it could ever be contradicted
   later, e.g. "(Barry's own rule, 2026-08-03)".
4. If it replaces something older, say so in the text: "supersedes the older
   X note". Old entries are marked superseded, never deleted.

BEFORE YOU STORE ANYTHING, CHECK IT IS NOT ALREADY THERE. Duplicated facts are
how the brain drifts: two copies of the same policy will eventually disagree and
nobody will know which one is current. Update the existing entry instead.

WHAT NOT TO PUT IN ALWAYS-ON:
- Whole uploaded documents, transcripts, or long drafts. Those go .md.
- Image and video descriptions (one is 3.7-4.3K characters -- ten would bury you).
  Media uploads already get .md added automatically.
- Finished deliverables. A draft belongs in Barry's approval queue, not your brain.
- Anything you are not sure is true. Ask him instead of storing a guess."""


def main():
    with memory.get_db() as conn:
        n = conn.execute(
            "UPDATE facts SET status='superseded' WHERE status='active' AND source_name=?",
            (SRC,),
        ).rowcount
    memory.add_fact("shared", BODY, SRC, title=TITLE)
    print("superseded %d old copies; seeded %d chars" % (n, len(TITLE) + 1 + len(BODY)))


if __name__ == "__main__":
    main()
