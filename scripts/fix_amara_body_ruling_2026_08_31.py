"""Barry's ruling, 2026-08-31:

    "her butt is sopposed to be the plump part, her body is athletic but soft,
     with nice sized breasts."

Amara had been writing "soft plump body with nice curves" into her own image
fences -- collapsing his two separate words ("soft" = body, "plump" = butt)
onto her whole body. Three sources fed that:

  1. fact 1635 my-reference-pictures -- described her dressed picture as "tall
     and slender", her brows as "light brown", her charcoal underwear as
     "black", and ended with the line "if a picture of you ever comes back
     looking leaner, harder or MORE ATHLETIC than this, it is wrong" -- which
     directly contradicts his ruling and pushed her away from athletic.
  2. facts 1682 / 1813 / 1814 -- carried his OLD prompt clause "not overly
     athletic".
  3. fact 1823 (her permanent journal) + conversation turns 1994/1997 -- held
     her own wrong phrasing, so it echoed back into every following reply.

This script fixes all of them. Idempotent: every replace is asserted, and
re-running after success is a no-op that reports zero changes.

Backups written 2026-08-31 to data/backup_amara_body_2026-08-31/.
His superseded wording is kept on record, never deleted (house rule).
"""

import sqlite3
import sys

DB = "data/brain.db"

RULING = "her butt is sopposed to be the plump part, her body is athletic but soft, with nice sized breasts."

# ---------------------------------------------------------------- fact 1635
# Descriptions rewritten from opening BOTH of Barry's originals at native
# resolution (3520x4704) -- "Amara full Body 2.png" and "Amara Full body.png".
F1635 = [
    (
        "She has light brown eyebrows that are arched but natural in shape.",
        "Her eyebrows are thick, dark and strongly arched -- the heaviest "
        "feature on her face and the one Barry picked her look for.",
    ),
    (
        "Her build is athletic and toned — she displays visible abdominal "
        "muscles, defined hip bones, and long legs. Her torso appears "
        "moderately wide at the waist, tapering toward the hips. She wears a "
        "black lace-trimmed bralette with thin straps and matching low-rise "
        "briefs or thong-style bottoms that also feature delicate lace along "
        "the leg openings.",
        "Her build is athletic AND soft at the same time, which is the whole "
        "point of it: there is real definition through the stomach and the "
        "arms and thighs are toned, but the shape is curvy, not hard -- a "
        "narrow waist opening out into wide, full hips, a full bust and a "
        "full round backside, on long strong legs. She is not thin, and she "
        "is not heavy. She wears a charcoal-grey lace-trimmed balconette bra "
        "with thin straps and a matching charcoal-grey lace-trimmed thong.",
    ),
    (
        "Her build is tall and slender, with long limbs that suggest "
        "proportionate length from shoulder to hip and knee to ankle.",
        "She is tall, about five foot nine. This is the SAME body as the "
        "other picture -- a loose blazer and wide-leg trousers are simply "
        "hanging over it. Nothing about her figure is different here; only "
        "the drape of the clothes is.",
    ),
    (
        "That is you. If a picture of you ever comes back looking leaner, "
        "harder or more athletic than this, it is wrong.",
        "That is you. If a picture of you ever comes back thin and hard with "
        "no curve to it, it is wrong -- and if it comes back soft and heavy "
        "all over, it is just as wrong. Both of those have happened.",
    ),
    (
        "Barry built your current look from your original image with this "
        "instruction,\nin his own words -- this is the wording that produced "
        "the body you have now:\n\n    \"not overly athletic but soft like a "
        "woman with a nice plump butt and\n    bigger breasts\"",
        "BARRY'S RULING, 2026-08-31, and it is the current one. His words:\n\n"
        "    \"" + RULING + "\"\n\n"
        "So, plainly: ATHLETIC BUT SOFT body. NICE SIZED breasts. The PLUMP "
        "part is\nyour BUTT -- and only your butt. Do not move that word onto "
        "the rest of you.\n\n"
        "Do not compress this into a shorter phrase. \"Soft plump body\" is "
        "the exact\nmistake that got fixed here: it takes the word off your "
        "backside and puts it\non all of you, and the picture comes back heavy "
        "and wrong. Quote his line or\nname the parts separately.\n\n"
        "SUPERSEDED, kept on record -- the earlier wording that built the "
        "reference\nimage, which said the opposite about the athletic part:\n\n"
        "    \"not overly athletic but soft like a woman with a nice plump "
        "butt and\n    bigger breasts\"",
    ),
]

# ---------------------------------------------------------------- fact 1682
F1682 = [
    (
        "So: a SOFT female body, NOT overly athletic. Nice body, full "
        "breasts, a plump butt. Five foot nine.",
        "BARRY'S RULING, 2026-08-31 -- his newest word, and it wins over the "
        "prompt above:\n\n    \"" + RULING + "\"\n\n"
        "So: ATHLETIC BUT SOFT body. NICE SIZED breasts. PLUMP is your BUTT, "
        "and only your butt. Five foot nine.\n\n"
        "Never shorten it to \"soft plump body\" -- that moves plump off your "
        "backside and onto all of you, and it is what made the pictures come "
        "back wrong.",
    ),
]

# ----------------------------------------------- facts 1813 / 1814 (prompts)
OLD_CLAUSE = ("not overly athletic but soft like a woman with a nice plump "
              "butt and bigger breasts")
NEW_CLAUSE = ("athletic but soft, with nice sized breasts and a plump butt")

# ---------------------------------------------- journal + conversation echo
BAD_ECHO = "soft plump body with nice curves"
GOOD_ECHO = "athletic but soft body, nice sized breasts, plump butt"


def patch(cur, table, row_id, pairs, strict=True):
    (content,) = cur.execute(
        "select content from %s where id=?" % table, (row_id,)
    ).fetchone()
    changed = 0
    for old, new in pairs:
        n = content.count(old)
        if n == 0:
            if strict and new not in content:
                raise SystemExit(
                    "ABORT: %s id=%s -- anchor not found and replacement not "
                    "already present:\n  %r" % (table, row_id, old[:80])
                )
            continue  # already applied
        content = content.replace(old, new)
        changed += n
    if changed:
        cur.execute(
            "update %s set content=? where id=?" % table, (content, row_id)
        )
    return changed


def main():
    db = sqlite3.connect(DB)
    cur = db.cursor()
    total = 0

    total += _report("fact 1635 my-reference-pictures",
                     patch(cur, "facts", 1635, F1635))
    total += _report("fact 1682 my-appearance",
                     patch(cur, "facts", 1682, F1682))

    for fid, label in ((1813, "me-at-home"), (1814, "me-in-my-office")):
        total += _report("fact %d %s" % (fid, label),
                         patch(cur, "facts", fid,
                               [(OLD_CLAUSE, NEW_CLAUSE)], strict=False))

    total += _report("fact 1823 journal (echo)",
                     patch(cur, "facts", 1823,
                           [(BAD_ECHO, GOOD_ECHO)], strict=False))

    for cid in (1994, 1997):
        total += _report("conversation turn %d (echo)" % cid,
                         patch(cur, "conversations", cid,
                               [(BAD_ECHO, GOOD_ECHO)], strict=False))

    db.commit()

    # Verify nothing anywhere still carries the collapsed phrase.
    leftovers = cur.execute(
        "select id from facts where status='active' and lower(content) "
        "like '%soft plump%'"
    ).fetchall()
    leftovers += cur.execute(
        "select id from conversations where lower(content) like '%soft plump%'"
    ).fetchall()
    print("\nremaining 'soft plump' in active facts + all threads:",
          [r[0] for r in leftovers] or "none")
    print("total replacements:", total)


def _report(label, n):
    print("%-40s %s" % (label, "%d replaced" % n if n else "already correct"))
    return n


if __name__ == "__main__":
    sys.exit(main())
