"""Teach Amara how to prompt EXPLICIT MOTION for her own clips.

Barry, 2026-09-18: "teach her how to prompt the explicit stuff... actual
fingers in and out motions."

Her shelf already had the stills side (explicit-and-tasteful-self-pictures),
his own prompt set (amara-explicit-render-prompts) and the LTX grammar
(ltx25-prompting). None of them covers motion over time, and the thing that
actually decides an explicit clip is our own plumbing: the AS VIDEO path
renders a STILL from her offer line and hands it to LTX as frame one, so the
same sentence has to serve both.

Re-runnable: ingest.teach upserts by title slug, so a second run replaces
rather than duplicating.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import ingest  # noqa: E402
import memory  # noqa: E402

TITLE = ("explicit-video-motion-clip-moving-masturbating-fingering-"
         "rhythm-in-and-out-ltx-video-of-myself")
DOC = os.path.join(os.path.dirname(__file__), "..",
                   "knowledge", "amara-explicit-video-motion.md")
OFFICE = "BusinessOps"


def main() -> None:
    with open(DOC, encoding="utf-8") as fh:
        text = fh.read()

    res = ingest.teach(OFFICE, "knowledge", text, title=TITLE)
    print("taught:", res)

    # The routing line has to survive whole: recall reads the FIRST PHYSICAL
    # line starting "USE WHEN:" out of content[:1200], and add_fact prepends a
    # TITLE line above it. Assert the stored line matches the file's, in full.
    facts = {f.get("source_name"): f
             for f in memory.get_active_facts_for_agent(OFFICE)}
    key = next((k for k in facts if k and "explicit-video-motion" in k), None)
    assert key, "fact not found after teach"
    stored = facts[key]["content"]

    want = next(l for l in text.splitlines() if l.startswith("USE WHEN:"))
    got = memory._skill_use_when({"content": stored}, 1200)
    assert got, "USE WHEN line not readable in the first 1200 chars"
    assert want.removeprefix("USE WHEN:").strip().startswith(got.strip()[:60]), \
        f"routing line truncated or altered:\n  want {want[:90]}\n  got  {got[:90]}"
    assert len(got) >= len(want.removeprefix("USE WHEN:").strip()) - 5, \
        f"routing line cut short: {len(got)} vs {len(want)}"

    print(f"ok: {key} ({len(stored)} chars), routing line {len(got)} chars intact")


if __name__ == "__main__":
    main()
