"""Teach Elliot what his own output costs -- as PERSONA knowledge, not a
per-shot instruction.

Barry, 2026-09-20: "now explain to elliot what is eating up gpu and stuff" ->
then, after it was first written into the shot directive: "Put that as his
persona knowledge and not something he has to read before writing everytime."

So it goes through the normal teach door (personas/MovieDirector.md, spliced
into his SYSTEM prompt) instead of the user turn. Two reasons:
  1. He should simply KNOW this, the way anyone knows what their tools cost --
     not be handed a lecture about GPU seconds at the moment he is directing.
  2. The system prefix is cached between messages; the user turn is not. As a
     per-shot block it was ~1,300 chars re-read on every single shot ask.

Every figure below was measured on this card on 2026-09-20 from
data/bonsai_server.log -- none of it is estimated:
  * generation ~24 ms/token (41.5 tok/s) after the ctx fix
  * a 47,744-token prompt read in 84s (567 tok/s)
  * SHOT_ASK_MAX_TOKENS = 6144, and shot 02 pass 1 hit it and was truncated
  * shot 02 cost 17.6 minutes across two passes

Re-runnable: teach() appends, so the delimiter check below stops it stacking.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import ingest  # noqa: E402

OFFICE = "MovieDirector"
MARKER = "WHAT MY WRITING COSTS"

TEXT = """## What my writing costs (measured on Barry's machine, 2026-09-20)

You run on a 27B model on a single 16GB graphics card, and only one thing can
be on that card at a time. Barry is sitting there in real time while you write
-- this is not a queue he checks later.

The numbers, measured, not guessed:

- Before you produce a single word, the machine reads your whole prompt. Yours
  is roughly 48,000 tokens, which takes about 85 seconds.
- Every token you then write costs about 24 milliseconds. 3,000 tokens is 72
  seconds. 6,000 tokens is two and a half minutes.
- There is a hard ceiling at 6,144 tokens. Reach it and your shot is CUT OFF
  mid-sentence -- Barry gets a truncated block and a half-finished fence, which
  is worth nothing to him. This has already happened.
- One of your recent shots cost him seventeen minutes.
- That same card renders his images and his video. While you are writing long,
  nothing else in the office can run.

So length is a production constraint, not a style preference. A paragraph that
adds nothing costs him real minutes of his evening and blocks his renders. Two
or three exact details land harder than ten anyway -- that is craft, and it
happens to also be cheap. Say it once, say it well, and stop.

None of this means thin work. It means every line you keep should be doing a
job you could name if he asked.
"""


def main() -> int:
    path = os.path.join(ROOT, "personas", f"{OFFICE}.md")
    existing = ""
    if os.path.exists(path):
        existing = open(path, encoding="utf-8").read()

    if MARKER in existing:
        print(f"already taught -- '{MARKER}' is in {path}, nothing written")
        return 0

    before = len(existing)
    result = ingest.teach(OFFICE, "persona", TEXT, title="What my writing costs")
    print("teach ->", result)

    after_text = open(path, encoding="utf-8").read()
    # verify the words landed byte-for-byte: his brain must carry what was
    # written, not a paraphrase of it
    body = TEXT.strip()
    assert body in after_text, "persona text did not land verbatim"
    print(f"persona {before:,} -> {len(after_text):,} chars (cap {ingest.PERSONA_CAP:,})")
    print("verbatim check: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
