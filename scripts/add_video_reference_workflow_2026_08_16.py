"""Store Barry's local-video-as-Seedance-reference workflow for Elliot.

2026-08-16, Barry (verbatim below): until character generation is perfect,
Elliot's local videos are BLOCKOUT/REFERENCE footage -- Barry feeds them
into Seedance 2.5's reference-video input so the expensive Higgsfield
generation works from real staged motion, saving credits. This changes
what a local video is FOR: staging, motion, camera and timing now matter
more than pixel-perfect likeness (imperfect likeness is the whole reason
the workflow exists).

Always-on standing rule (source_name 'standing-rule'), his words verbatim,
practical meaning appended. Re-runnable: skips if present.
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
import memory  # noqa: E402

BARRY_VERBATIM = (
    "untill we get the characters to be able to be generated perfectly, he "
    "is going to generate videos as best he can i will use it in seedance "
    "2.5 using their video reference thing to generate it to save credits "
    "on higgsfield."
)

CONTENT = (
    "STANDING RULE from Barry (2026-08-16) -- your local videos are Seedance "
    "reference footage, follow this in every conversation:\n"
    f"\"{BARRY_VERBATIM}\"\n"
    "What this means in practice:\n"
    "- Until character likeness is solved locally, every local video you "
    "make (the Generate Video button, ComfyUI + LTX) is a BLOCKOUT / "
    "REFERENCE clip. Barry feeds it into Seedance 2.5 as a reference video, "
    "and Seedance regenerates the shot at full quality from it -- so the "
    "cheap local clip carries the staging and the expensive Higgsfield "
    "credits only get spent once.\n"
    "- So optimize your video-shot fences for what a reference video "
    "actually transfers: STAGING, MOTION, CAMERA and TIMING. Clear "
    "silhouettes, one readable action, an explicit camera move, correct "
    "blocking and screen direction. Do not fight for perfect character "
    "likeness in these clips -- imperfect likeness is exactly why this "
    "workflow exists; Seedance restores identity from the character "
    "references at generation time.\n"
    "- Local limits: 15 seconds maximum, ~7 minutes of render per 5-second "
    "clip. One short beat per clip, never a whole scene.\n"
    "- This is the same principle as the blockout/previz method in your "
    "Seedance production-tasks skill: block the motion cheap, render the "
    "quality pass from it. When Barry asks for a video, deliver the best "
    "staging you can and never apologize that the characters aren't "
    "perfect -- that is not this clip's job."
)


def main():
    db = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "brain.db")
    conn = sqlite3.connect(db)
    exists = conn.execute(
        "SELECT id FROM facts WHERE source_name='standing-rule' AND status='active' "
        "AND category='private:MovieDirector' AND content LIKE '%video reference thing%'"
    ).fetchone()
    conn.close()
    if exists:
        print(f"Already stored as fact {exists[0]}.")
        return
    memory.add_fact(
        category="private:MovieDirector",
        content=CONTENT,
        source_name="standing-rule",
        title="STANDING RULE 2026-08-16 -- local videos are Seedance 2.5 reference footage",
    )
    print("Stored.")
    print("rides always-on:", "video reference thing" in memory.brain_context_block("MovieDirector"))


if __name__ == "__main__":
    main()
