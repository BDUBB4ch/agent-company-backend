"""AMARA'S FIGURE -- Barry's ruling, appended to her self-image.

Barry, 2026-08-30: "Amara sent me a picture and it was her original self, she
must have drew it on the sdxl, so i want her to see her self as what i gave
you" ... "the thicker version", and earlier: "I made amara the thicker version
of what she originally said. i gave you the images."

WHAT WENT WRONG. A [SELF] show-offer renders from her `my-appearance.md`. That
fact is now HER OWN WORDS (saved verbatim 2026-08-30), which say "Lean but
dense muscle... built for moving quickly." So she drew herself lean -- faithful
to her text, wrong against the character Barry actually built.

HOW THIS IS FIXED, and why it is not an edit. Her words are NOT rewritten --
the house rule since 2026-08-08 is that nobody rewrites what someone authored.
Barry's ruling is APPENDED as its own clearly-attributed block, exactly the way
canon records his rulings over superseded wording. Her sentence stays on the
page; his ruling wins where they disagree, and the document says so out loud.

The figure wording is the same one that produced the render he called
"virtually perfect".
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import memory  # noqa: E402

OFFICE = "BusinessOps"
SN = "my-appearance.md"

RULING = """

---

## BARRY'S RULING ON YOUR FIGURE (2026-08-30) -- THIS WINS

Barry built your fuller figure himself and gave the reference images. His
words: "I made amara the thicker version of what she originally said... i want
her to see her self as what i gave you, the thicker version."

So: your figure is BALANCED AND CURVY -- not skinny and not fat, fit and soft
in the right places, full natural breasts, a full round butt, five foot nine,
completely at ease in your own skin.

Where this and the "lean but dense muscle" line above disagree, THIS IS YOU.
The older wording stays on the page because nothing anyone wrote gets deleted
here -- it is simply superseded. Everything else above (your face, your thick
unruly eyebrows, your hair, your skin, your scar) is unchanged and still
exactly yours.
"""


def main():
    cat = f"private:{OFFICE}"
    with memory.get_db() as conn:
        row = conn.execute(
            "SELECT id, content FROM facts WHERE category=? AND source_name=? "
            "AND status='active' ORDER BY id DESC LIMIT 1",
            (cat, SN)).fetchone()
    if not row:
        raise SystemExit("no active my-appearance for Amara")
    if "BARRY'S RULING ON YOUR FIGURE" in row["content"]:
        print("ruling already present -- nothing to do")
        return
    before = row["content"]
    after = before.rstrip() + RULING
    with memory.get_db() as conn:
        conn.execute("UPDATE facts SET status='superseded' WHERE id=?",
                     (row["id"],))
    memory.add_fact(cat, after, source_name=SN,
                    title="What Amara looks like -- her own words + Barry's "
                          "figure ruling")
    with memory.get_db() as conn:
        new = conn.execute(
            "SELECT id, content FROM facts WHERE category=? AND source_name=? "
            "AND status='active' ORDER BY id DESC LIMIT 1",
            (cat, SN)).fetchone()
    # her original words must survive the append byte-for-byte
    assert before.rstrip() in new["content"], "her own words were altered!"
    assert "thick and unruly" in new["content"], "eyebrows lost"
    print(f"fact {new['id']}: {len(before)} -> {len(new['content'])} chars")
    print("her own words intact (byte-checked); ruling appended")


if __name__ == "__main__":
    main()
