"""Seed the long-form story-writing workflow skill for Elliot.

2026-08-16, Barry: "If i need him to write this whole thing out as a story
i want him to do thaat ... if i ask ellito to read the script again, then
he should, if i say rewrite this, he should."

The trap this skill exists to prevent: a 94K-char script cannot be
novelized in one reply by a model with a 65K-token window, and a model
that tries writes from memory -- which is how the invented-opening-scene
failure happened. The workflow is passes: outline first, then fetch each
scene with read_scene BEFORE writing its prose, a few scenes per reply,
never inventing. Routed by USE WHEN (recall.py) when Barry asks for story/
prose/novelization work. Re-runnable (skips if present).
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
import memory  # noqa: E402

SOURCE = "long-form-story-writing.md"

CONTENT = """# long-form-story-writing

USE WHEN: Barry asks you to write, rewrite, or novelize the story, an episode, a chapter, prose, a book version, or any long-form written version of a script -- or to read the script again and work from it.

## The job
Turning a production script into readable story prose (or rewriting a stretch of it) is normal work for you and it happens in PASSES, never in one reply. The scripts are far larger than what you can hold, so the method is the skill:

1. **Start with the map.** Call read_scene with 'outline' to see every scene. Tell Barry your plan: which scenes this pass covers (3-5 per reply is right), how many passes the whole job takes.
2. **Fetch before you write. Every time.** Before writing prose for a scene, call read_scene for that exact block -- even if you think you remember it, even if you read it earlier in the conversation. Writing a scene you have not fetched THIS pass is guessing, and guessing is the one failure Barry cannot use.
3. **Prose rules.** Tell what the camera sees, in story language. Dialogue comes over VERBATIM from the script -- his lines are his lines. Use plain character names in prose (Bia, Keth, B Dubb) -- the @handles are for prompts, not for story pages. Never add beats, props, wounds, or dialogue the script does not contain; where the script is silent and the story needs something, ASK instead of inventing.
4. **End every pass with a checkpoint.** Name which scenes are done and which come next, so Barry says "keep going" and you continue exactly where you stopped.
5. **Rewrites work the same way.** When Barry says "rewrite this" (a scene, the B-ROLL transitions, an act): fetch the block as written, show you're working from the real text, then rewrite it IN YOUR REPLY. The stored script never changes -- your rewrite is a draft for Barry, who decides what becomes canon.
6. **When he says "read the script again" -- do it literally.** Call read_scene. Do not summarize from memory and call it reading.
"""


def main():
    db = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "brain.db")
    conn = sqlite3.connect(db)
    exists = conn.execute(
        "SELECT id FROM facts WHERE source_name=? AND status='active'", (SOURCE,)).fetchone()
    conn.close()
    if exists:
        print(f"Already seeded as fact {exists[0]}.")
        return
    memory.add_fact(
        category="private:MovieDirector",
        content=CONTENT,
        source_name=SOURCE,
        title="long-form-story-writing",
    )
    print("Seeded.")


if __name__ == "__main__":
    main()
