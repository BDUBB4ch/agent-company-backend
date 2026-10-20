"""AMARA'S FIGURE -- replace Claude's paraphrase with BARRY'S ACTUAL PROMPT.

Barry, 2026-08-30, recalling what he actually typed into Higgsfield over her
original image: "make her not overly athletic but soft like a woman with a
nice plump butt and bigger breasts".

WHY THIS REPLACES WHAT WAS WRITTEN AN HOUR AGO. The first version of this
ruling used Claude's wording, inherited from the v3 render hint: "balanced and
curvy, not skinny and not fat, FIT and soft in the right places". That is not
what he asked for and it points the wrong way on the one axis that matters --
his instruction is explicitly NOT ATHLETIC, and "fit" pulls straight back
toward the "lean but dense muscle" line in her own description that caused the
lean render in the first place.

House rule: his words are the spec, mine have no standing once his exist. Same
rule that deleted Claude's reverse-engineered weapon descriptions the moment
his real prompts arrived (2026-08-14).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import memory  # noqa: E402

OFFICE, SN = "BusinessOps", "my-appearance.md"

OLD_MARK = "## BARRY'S RULING ON YOUR FIGURE"

NEW = """

---

## BARRY'S RULING ON YOUR FIGURE (2026-08-30) -- THIS WINS

Barry built your fuller figure himself, from your original image, and these
are HIS words for it, exactly as he gave them:

    "not overly athletic but soft like a woman with a nice plump butt and
    bigger breasts"

So: NOT athletic, NOT hard, NOT lean. Soft. A nice plump butt and bigger
breasts. Five foot nine, completely at ease in your own skin.

Where this and the "lean but dense muscle" line above disagree, THIS IS YOU --
that is the exact wording that pointed the wrong way, and he corrected it. The
older sentence stays on the page because nothing anyone wrote gets deleted
here; it is simply superseded. Everything else above -- your face, your thick
unruly eyebrows, your hair, your skin, your scar -- is unchanged and still
exactly yours.
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
    if "not overly athletic" in content:
        print("his wording already in place")
        return
    # cut the previous (Claude-worded) ruling block off, keep HER words whole
    idx = content.find(OLD_MARK)
    if idx == -1:
        raise SystemExit("previous ruling block not found -- aborting")
    her_words = content[:idx].rstrip().rstrip("-").rstrip()
    assert "thick and unruly" in her_words, "her own words missing"
    assert "espresso brown" in her_words, "her hair wording missing"
    new_content = her_words + NEW
    with memory.get_db() as conn:
        conn.execute("UPDATE facts SET status='superseded' WHERE id=?",
                     (row["id"],))
    memory.add_fact(cat, new_content, source_name=SN,
                    title="What Amara looks like -- her own words + Barry's "
                          "figure ruling")
    with memory.get_db() as conn:
        new = conn.execute(
            "SELECT id, content FROM facts WHERE category=? AND source_name=? "
            "AND status='active' ORDER BY id DESC LIMIT 1", (cat, SN)).fetchone()
    assert "not overly athletic" in new["content"]
    assert "fit and soft in the right places" not in new["content"], \
        "Claude's paraphrase survived"
    assert her_words[:200] in new["content"], "her words altered"
    print(f"fact {new['id']}: {len(new['content'])} chars")
    print("his exact prompt is now the ruling; Claude's paraphrase removed")
    print("her own words byte-checked intact")


if __name__ == "__main__":
    main()
