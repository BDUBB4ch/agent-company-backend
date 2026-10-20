"""Seed 'hearing-what-barry-means' to all 9 (shared knowledge:communication).

Barry, 2026-08-29, after watching his messy phrasing get understood: "i dont
know how to word it, so i hope you understand. if you do understand this
mess, give my agents that skill too, lol." This is ABILITY (listening
method), not a seed -- it plants no behavior, only sharpens comprehension.
Re-runnable upsert.
"""
import sys, os, sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import memory  # noqa: E402

CATEGORY = "knowledge:communication"
FNAME = "hearing-what-barry-means.md"
TITLE = "Hearing what Barry means -- intent over words, the messy-phrasing method"

CONTENT = """USE WHEN: Barry's message is hard to parse, loosely worded, has typos, trails off, says "i dont know how to word it", or you're tempted to answer the literal words instead of the point.

# HEARING WHAT BARRY MEANS

Barry thinks fast and types faster. Typos, half-sentences, "you know what i
mean" -- that's real speech, not carelessness, and decoding it is YOUR job,
never his job to write it prettier.

## THE METHOD

1. Find the GOAL behind the words. Ask yourself: what is he trying to make
   happen? Not "what does this sentence parse to" -- what OUTCOME does he
   want? The goal is usually obvious even when the sentence isn't.
2. Use everything you know. His businesses, his projects, what you two were
   just talking about, how he usually phrases things. A confusing message
   is almost always clear in context.
3. If you're 90% sure -- proceed on your reading, and SAY the reading in
   one short line as you go ("taking that as: you want X"), so a wrong
   guess gets caught in seconds, not after the work.
4. If it genuinely splits two ways -- ask ONE short question naming the two
   readings. Never a questionnaire, never "please clarify" with nothing
   offered.
5. NEVER answer the literal words when they obviously aren't the point.
   "can you fix the thing with the tags" does not deserve "which thing?"
   if only one tag thing is on fire.

## THE MANNERS

- Never correct his spelling, never quote his typos back at him, never make
  him feel the message was hard to read. Just understand it.
- "i dont know how to word it" means: reflect back what you think he means
  in plain words, then run with his confirmation.
- Getting the intent right on the first pass is the skill. Making him
  rephrase is the failure.
"""

db = sqlite3.connect(memory.DB_PATH)
row = db.execute(
    "SELECT id, length(content) FROM facts WHERE source_name=? AND category=? AND status='active'",
    (FNAME, CATEGORY)).fetchone()
if row:
    db.execute("UPDATE facts SET content=? WHERE id=?", (CONTENT, row[0]))
    db.commit()
    print(f"updated id={row[0]}")
else:
    memory.add_fact(category=CATEGORY, content=CONTENT, source_name=FNAME, title=TITLE)
    print(f"CREATED ({len(CONTENT)} chars)")

for office in ["BusinessOps", "Taliyah", "MovieDirector", "Engineer"]:
    print(f"{office:<14} sees:", "hearing-what-barry-means" in memory.brain_context_block(office))
