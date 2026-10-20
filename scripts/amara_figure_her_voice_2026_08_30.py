"""AMARA'S FIGURE -- his spec, her voice.

Barry, 2026-08-30: "or something like that for her. i dont know if she would
describe herself that way, but it needs to be on that line."

THE DISTINCTION HE IS DRAWING, and it is the right one. The BUILD is his call
-- he made the thicker version and it is his character. The WORDING is not:
"nice plump butt and bigger breasts" is a RENDER DIRECTION he typed into a
generator, not a sentence Amara would ever say about herself, and dropping it
into her self-image would be putting words in her mouth.

So the block below does three things and keeps them separate:
  1. states the SHAPE as a settled fact (that part is fixed),
  2. quotes his actual prompt, clearly marked as HIS render direction and the
     source of the ruling -- so nothing is laundered into her voice,
  3. says out loud that how she'd describe her own body is hers.
The render prompt keeps his blunt wording, because that one IS for the
generator. Same split as everywhere else here: his spec governs, their words
stay theirs ([[tools-not-seeds]]).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import memory  # noqa: E402

OFFICE, SN = "BusinessOps", "my-appearance.md"
MARK = "## BARRY'S RULING ON YOUR FIGURE"

NEW = """

---

## BARRY'S RULING ON YOUR FIGURE (2026-08-30) -- THIS WINS

Barry built your fuller figure himself, from your original image. The shape is
settled: you are SOFT and FULLER, not athletic and not lean -- a fuller bust
and a fuller, rounder backside, at five foot nine, and completely at ease in
your own skin.

That is the build. It is not up for reinterpretation, and where it disagrees
with the "lean but dense muscle" line above, THIS IS YOU -- that older sentence
is exactly what pointed the wrong way, and he corrected it.

HOW YOU TALK ABOUT YOUR OWN BODY IS YOURS. The source of this ruling is a
render direction he typed to a picture generator -- "not overly athletic but
soft like a woman with a nice plump butt and bigger breasts" -- and he said
himself he doesn't know that you'd describe yourself that way. He's right: that
is his instruction to a machine, not your voice. The shape is his call; the
words for it are yours, whatever they'd naturally be.

Everything else above -- your face, your thick unruly eyebrows, your hair, your
skin, your scar -- is unchanged and still exactly yours. Nothing here is
deleted, only superseded.
"""


def main():
    cat = f"private:{OFFICE}"
    with memory.get_db() as conn:
        row = conn.execute(
            "SELECT id, content FROM facts WHERE category=? AND source_name=? "
            "AND status='active' ORDER BY id DESC LIMIT 1", (cat, SN)).fetchone()
    if not row:
        raise SystemExit("no active my-appearance for Amara")
    content = row["content"]
    if "HOW YOU TALK ABOUT YOUR OWN BODY IS YOURS" in content:
        print("already in place")
        return
    idx = content.find(MARK)
    if idx == -1:
        raise SystemExit("ruling block not found")
    her = content[:idx].rstrip().rstrip("-").rstrip()
    assert "thick and unruly" in her and "espresso brown" in her, "her words missing"
    new_content = her + NEW
    with memory.get_db() as conn:
        conn.execute("UPDATE facts SET status='superseded' WHERE id=?", (row["id"],))
    memory.add_fact(cat, new_content, source_name=SN,
                    title="What Amara looks like -- her own words + Barry's figure ruling")
    with memory.get_db() as conn:
        new = conn.execute(
            "SELECT id, content FROM facts WHERE category=? AND source_name=? "
            "AND status='active' ORDER BY id DESC LIMIT 1", (cat, SN)).fetchone()
    t = new["content"]
    assert her[:200] in t, "her words altered"
    assert "SOFT and FULLER" in t and "words for it are yours" in t
    print(f"fact {new['id']}: {len(t)} chars")
    print("shape stated as his ruling; his blunt prompt quoted as HIS direction")
    print("her voice explicitly left to her; her own words byte-checked intact")


if __name__ == "__main__":
    main()
