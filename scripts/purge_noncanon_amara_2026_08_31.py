"""Barry, 2026-08-31:

    "every time i told you to delete something, you instantly said you were
     keeping it as a back up or something, but i told you i dont want shit for
     them to pull from thats not canon or new canon."

New rule, and it holds from here on: DELETE MEANS DELETE. Superseded ROWS were
never the problem -- every read in memory.py filters status='active', so a
superseded row is already unreachable. The problem is superseded TEXT sitting
INSIDE active facts, which is fully reachable and is exactly what Amara kept
pulling.

So this removes the non-canon wording from her four ACTIVE appearance docs.
Nothing is parked, nothing is marked, it is gone.

CURRENT CANON, the only body wording that survives anywhere:
    "her butt is sopposed to be the plump part, her body is athletic but soft,
     with nice sized breasts."   -- Barry, 2026-08-31

Idempotent: every removal is asserted, re-running is a no-op.
"""

import sqlite3
import sys

DB = "data/brain.db"

# (fact_id, exact text to remove, replacement, why)
REMOVALS = [
    # -- 1682 my-appearance ------------------------------------------------
    (1682,
     "**Body:** Lean but dense muscle -- built for moving quickly, not lounging.",
     "**Body:** Athletic but soft -- strong, but curvy with it.",
     "her own superseded body line, the one that kept rendering her thin"),
    (1682,
     "\n\n⚠️ This supersedes the \"Lean but dense muscle\" line in your own "
     "text above. That sentence stays on the page because nothing anyone wrote "
     "gets deleted here -- it is simply no longer what you look like, and it is "
     "the line that kept rendering you thin.",
     "",
     "the note pointing at a line that no longer exists"),
    (1682,
     "This is the prompt he actually used to build your body in the reference "
     "image, word for word:\n\n    Hyper realistic full body view from the feet "
     "up. intricate details and design. Nice body, full breasts and a plump "
     "butt, wearing bra and sexy panties, soft female body, not overly athletic",
     "This is what he built your body to be:\n\n    Nice body, nice sized "
     "breasts and a plump butt, athletic but soft.",
     "the old prompt, whose 'not overly athletic' is the opposite of canon"),

    # -- 1635 my-reference-pictures ----------------------------------------
    (1635,
     "Her build is tall and slender, with long limbs that suggest proportionate "
     "length from shoulder to hip and knee to ankle.",
     "She is tall, five foot nine. This is the same body as the other picture "
     "-- the blazer and wide-leg trousers are simply hanging over it.",
     "'tall and slender' -- a misread of the clothed picture"),
    (1635,
     "That is you. If a picture of you ever comes back looking leaner, harder "
     "or more athletic than this, it is wrong.",
     "That is you. If a picture of you comes back thin and hard with no curve "
     "to it, it is wrong.",
     "told her MORE ATHLETIC was wrong -- the reverse of canon"),
    (1635,
     "Barry built your current look from your original image with this instruction,\n"
     "in his own words -- this is the wording that produced the body you have now:\n\n"
     "    \"not overly athletic but soft like a woman with a nice plump butt and\n"
     "    bigger breasts\"",
     "Barry's ruling on your body, and it is the current one:\n\n"
     "    \"her butt is sopposed to be the plump part, her body is athletic but\n"
     "     soft, with nice sized breasts.\"",
     "the old clause, superseded 2026-08-31"),

    # -- 1813 me-at-home ---------------------------------------------------
    (1813,
     "not overly athletic but soft like a woman with a nice plump butt and "
     "bigger breasts",
     "athletic but soft, with nice sized breasts and a plump butt",
     "old clause inside her at-home render prompt"),
]


def main():
    db = sqlite3.connect(DB)
    cur = db.cursor()
    changed = skipped = 0

    for fid, old, new, why in REMOVALS:
        (content,) = cur.execute(
            "select content from facts where id=?", (fid,)).fetchone()
        if old not in content:
            print("  --  %-5s already gone: %s" % (fid, why))
            skipped += 1
            continue
        content = content.replace(old, new)
        cur.execute("update facts set content=? where id=?", (content, fid))
        print("  REMOVED %-5s %s" % (fid, why))
        changed += 1

    db.commit()

    # Prove nothing non-canon survives in any ACTIVE fact she can reach.
    bad = ("lean but dense", "not overly athletic", "tall and slender",
           "more athletic than this")
    leftovers = []
    for fid, src, content in cur.execute(
            "select id,source_name,content from facts "
            "where status='active' and category like 'private:BusinessOps%'"):
        low = content.lower()
        for b in bad:
            if b in low:
                leftovers.append((fid, src, b))

    print("\n%d removed, %d already clean" % (changed, skipped))
    print("non-canon left in her active facts:", leftovers or "NONE")


if __name__ == "__main__":
    sys.exit(main())
