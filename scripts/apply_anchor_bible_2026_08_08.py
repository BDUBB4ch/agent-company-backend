"""Install Barry's 2026-08-08 CHARACTER ANCHORS as the top-authority section of
the canon bible, in BOTH places that hold it:

  1. data/barry-character-canon.md on disk  (was STALE -- 12,475 chars, missing
     every 2026-08-07 and 2026-08-08 ruling that only ever landed in the brain)
  2. facts.id=592, category knowledge:talia_crew, source_name
     barry-character-canon.md  (the live copy all 9 agents read; also Elliot's
     PINNED skill, so it prints in full on every one of his messages)

His words go in VERBATIM. Nothing is deleted -- the anchor section states its
own precedence and the superseded wording stays below it, which is the same
convention his own RULED BY BARRY notes already use.

Run once from the repo root:  venv/Scripts/python.exe scripts/apply_anchor_bible_2026_08_08.py
Safe to re-run: it replaces the anchor section by its delimiters rather than
stacking copies.
"""
import datetime
import json
import os
import sqlite3
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(REPO, "data", "brain.db")
DISK = os.path.join(REPO, "data", "barry-character-canon.md")
FACT_ID = 592

BEGIN = "=== BEGIN 2026-08-08 CHARACTER ANCHORS ==="
END = "=== END 2026-08-08 CHARACTER ANCHORS ==="

ANCHORS = """
===============================================================
""" + BEGIN + """
BARRY'S CHARACTER ANCHORS -- given verbatim 2026-08-08.
HIS WORDS. This is the Bible.

PRECEDENCE: these anchors are the most recent thing he has said about how
each character LOOKS. Where an anchor and anything below it in this document
disagree, THE ANCHOR WINS. Nothing below is deleted -- superseded wording is
kept on record exactly as his earlier rulings are. The anchors cover LOOK
only; everything else in this document (roles, backstory, personality,
relationships, combat, downtime wardrobe, Vor'Shara's physiology and her tie
to Bia) is untouched and still authoritative.

Copy an anchor as-is. Do not paraphrase it, do not "improve" the wording, do
not clean up his parentheses or weight syntax, and never write your own prose
description of a character and save it as canon.
===============================================================

@B DUBB: Stocky Black American Indian male, brownish-red skin tone, aged-down
26-32, fuller rounded salt-and-pepper goatee. All-black tactical gear -- black
hoodie, black cargo pants, black boots, black baseball cap pulled low. ((Gold
number 4 pendant necklace with high-quality diamonds -- always visible, always
catching every available light source)). Belt: all-black Glock .40, utility
knife in sheath, tactical gloves tucked at hip. No phone, no smartwatch, no
earbuds, no trackers on jobs.

@BIA: Athletic alien woman, noticeably pointed ears, deep-purple and gold
double-ringed fractal irises -- non-glowing, non-emissive. Subtle gold alien
spots across skin. Faint iridescent spots on temples only. Grey and black
form-fitting tactical suit. Multi-tool holstered on right hip always. Alien
pistol left hip silenced mode.

@YANNAH: Young alien woman ~19 years old, noticeably pointed ears, green and
brown double-ringed fractal irises -- non-glowing. Subtle gold freckle-like
spots around upper cheeks and outer eye area. Short asymmetrical wavy hair one
side shaved. Grey and black form-fitting tactical jumpsuit with teal piping.
Alien pistol with tech modifications. Forearm bot controller in sleeve.

@TAZZ: Alien woman, light skin like a white woman, noticeably pointed ears,
pink and blue double-ringed irises -- non-glowing. Two long dark braids always
secured tight. Very strong, visibly muscular build. All-black form-fitting
one-piece tactical jumpsuit -- SLEEVELESS. Alien pistol rarely drawn.
Mutation: unusually strong for her species, does not feel much pain, skin
highly durable.
  (Wardrobe corrected by Barry the same day, in his words: "one change to
   Tazz's colors of clothing. It should be all black" / "jumpsuit" /
   "onepiece form fitting" / "tactical" / "just like in her images. the new
   ones". The anchor line above already carries that correction.)

@KETH: Alien male approximately 4 feet tall. Smooth gray skin slightly
textured like weathered pale stone. Slightly Elongated enlarged cranium. No
hair. Large GREEN eyes -- green iris with a dark pupil, no visible white /
no sclera. Small barely-pointed ears. Lean compressed build. Gray facility
jumpsuit -- worn, slightly torn at collar. No shoes. Raw wrists from
restraints.
  (Two corrections Barry made the same day, in his words. EYES: his anchor
   first said "Large fully dark eyes -- no visible iris or white"; asked
   about the clash with his 2026-08-04 ruling he answered "it should be
   green, just like the new images" -- so GREEN, matching that ruling, and
   the "fully dark" wording is superseded. SKIN: asked to choose between the
   anchor's "slightly textured like weathered pale stone" and the earlier
   same-day "SLIGHTLY WRINKLED skin", he ruled "Keth go with anchor" -- so
   the anchor wording above stands and SLIGHTLY WRINKLED is superseded.)

@VORSHARA (Lady Vor'Shara Vel) -- Barry: "that is the original prompt that
created her", and "Lady Vor, go with what i gave you". It therefore wins over
the Canon Locked v2.2 wording further down this document. Verbatim, including
his weights and parentheses -- do NOT clean up the syntax:

Lady Vor'Shara Vel, balanced curvy elegant body,
smooth greyish-white skin, four electric-blue eyes,
long organic tendrils with gold rings, purple gemstones, emerald inlays,
gold nose ring with gem-studded chain to ear,
gold and diamond necklace with glowing unknown gem,
((fully sheer pale-purple couture gown:1.5)),
((translucent fabric:1.4)), ((see-through material behavior:1.3)), (translucent fabric:1.4)), ((see-through material behavior:1.3)), ((fabric revealing natural areola and breast skin tone beneath)), and pubic hair on her lady parts
gold filigree, alien glyph embroidery, gemstone inlays,
((gold detailing contouring the body:1.3)),
structured supportive bodice, couture lift,
flowing sheer layers, shimmering gold threads,
((No text))

  Still true from her Canon Locked v2.2 entry, just not carried in the anchor:
  the tendrils are NOT hair (they move, they have weight); she has no hair of
  any kind; the four eyes are TWO PAIRS STACKED VERTICALLY with dark vertical
  slit pupils; smooth wide face, small nose, full lips, alien dot-markings on
  the cheeks -- alien but never monstrous. Her sanctum is the interior garden
  atrium, never a violet chamber.
  ONE THING THE PROMPT DOES NOT SPEAK TO: whether the eyes glow at rest. His
  2026-08-04 ruling -- "no, glow, only when angry, 163 nits" -- is a separate
  explicit ruling and STANDS. Read "electric-blue" as the colour, not as a
  permanent glow state. Baseline: no glow.

---------------------------------------------------------------
WHERE THESE ANCHORS OVERRIDE SOMETHING BELOW -- listed so nothing changes
silently. Every one of these is Barry's newer wording beating his older
wording; none of it is a Claude judgement call.
---------------------------------------------------------------
* KETH SKIN -- anchor: smooth gray, slightly textured like weathered pale
  stone. Supersedes "SLIGHTLY WRINKLED skin" (2026-08-08, earlier) and the
  2026-08-07 "WRINKLED, BUT LESS EXTREME" note. Ruled: "Keth go with anchor".
* KETH EARS -- anchor: SMALL, barely-pointed. This agrees with his long-
  standing small/low-profile spec and with the 2026-08-08 head/ear ruling.
  It CONTRADICTS the line in the SPECIES block below that reads "LARGE
  prominent pointed ears standing off the skull" -- that line is wrong; the
  anchor governs. Ears stay small, low-profile, and SEPARATE from the
  cranium silhouette (never merged into it, never football-shaped).
* KETH EYES -- green iris, dark pupil, no sclera. Unchanged; the anchor's
  first "fully dark" wording was withdrawn by him the same day.
* TAZZ IRISES -- anchor: PINK AND BLUE double ring. This differs from the
  2026-08-07/08 wording "VIOLET outer + MAGENTA-PINK inner". The anchor is
  newer and governs. FLAGGED FOR HIM -- if the violet/magenta pair was
  meant to stand, he only has to say so.
* TAZZ OUTFIT -- anchor: ALL-BLACK one-piece form-fitting SLEEVELESS
  tactical jumpsuit. Consistent with the older "black sleeveless turtleneck
  one-piece tactical jumpsuit"; supersedes any "grey and black" wording.
* YANNAH SPOTS -- anchor: subtle gold freckle-like spots around the upper
  cheeks and outer eye area. This REVERSES the 2026-08-07 "YANNAH HAS NO
  SPOTS" ruling. The anchor is newer and governs. FLAGGED FOR HIM.
* BIA / YANNAH TACTICAL SUIT COLOUR -- anchor: GREY AND BLACK form-fitting.
  Supersedes the older plain "black fitted". (Tazz is the all-black one.)
* B DUBB VEST -- the anchor does not mention the black tactical plate-carrier
  vest. It does not deny it either, and the vest was ruled canon on
  2026-08-03 ("the vest is to be added as canon, thats why its in the
  renders"), worn OVER the hoodie with the #4 pendant OVER the vest. Treated
  as still canon, not dropped. FLAGGED FOR HIM.
* NOT TOUCHED BY THE ANCHORS: every caption-training rule below (invariant
  traits are learned through the @trigger and do not belong in a caption),
  Bia's beaded-ring iris description and her temples+cheekbones flecks, the
  telling-them-apart rules, the same-species rule for Bia/Yannah/Tazz, and
  the correction log.
""" + END + """
===============================================================

"""


def splice(doc: str) -> str:
    """Insert (or replace) the anchor section immediately after the header."""
    if BEGIN in doc and END in doc:
        head = doc[: doc.index("===============================================================\n" + BEGIN)]
        tail = doc[doc.index(END) + len(END) :]
        tail = tail.split("===============================================================\n", 1)[-1]
        return head + ANCHORS.lstrip("\n") + tail
    marker = "document, the RENDER is wrong."
    if marker not in doc:
        raise SystemExit("header marker not found - refusing to guess where to splice")
    cut = doc.index(marker) + len(marker)
    return doc[:cut] + "\n\n" + ANCHORS.lstrip("\n") + doc[cut:].lstrip("\n")


def main() -> None:
    stamp = "2026-08-08"
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM facts WHERE id = ?", (FACT_ID,)).fetchone()
    if row is None:
        raise SystemExit(f"fact {FACT_ID} not found")
    live = row["content"]

    # --- backups, before anything is written ---
    bdir = os.path.join(REPO, "data")
    with open(os.path.join(bdir, f"backup_fact592_canon_before_anchors_{stamp}.md"), "w", encoding="utf-8") as fh:
        fh.write(live)
    with open(os.path.join(bdir, f"backup_disk_canon_before_anchors_{stamp}.md"), "w", encoding="utf-8") as fh:
        fh.write(open(DISK, encoding="utf-8").read())
    allfacts = [dict(r) for r in conn.execute("SELECT * FROM facts WHERE category = 'knowledge:talia_crew'")]
    with open(os.path.join(bdir, f"backup_talia_crew_facts_{stamp}.json"), "w", encoding="utf-8") as fh:
        json.dump(allfacts, fh, indent=1)

    # --- the live brain copy is the fuller document; carry over the two
    #     Vor'Shara lines where the DISK copy is the newer one (it has the
    #     2026-08-04 anger-only glow ruling and the brain copy does not) ---
    fixes = [
        (
            "* Eyes: FOUR eyes — two pairs stacked vertically. ALL FOUR are icy pale blue with dark vertical slit pupils. They do NOT glow (RULED BY BARRY 2026-08-04: \"eyes were never glowing, just icy blue\" - supersedes the earlier wording \"ALL FOUR glow luminescent blue - active, unmistakable, never subtle\")",
            "* Eyes: FOUR eyes — two pairs stacked vertically. ALL FOUR are icy pale blue with dark vertical slit pupils. At rest they do NOT glow (RULED BY BARRY 2026-08-04: \"eyes were never glowing, just icy blue\" - supersedes the earlier wording \"ALL FOUR glow luminescent blue - active, unmistakable, never subtle\")\n* Eye glow = ANGER ONLY, and it has a spec (RULED BY BARRY 2026-08-04: \"no, glow, only when angry, 163 nits\"). Baseline is no glow; the glow is an emotional tell, not a constant. Do not render or prompt glowing eyes unless the beat is anger — and when it is, it is a measured 163 nits, not \"unmistakable, never subtle\"",
        ),
        (
            "* Four electric-blue glowing eyes — adapted for low-light and reading micro-expressions",
            "* Four electric-blue eyes — adapted for low-light and reading micro-expressions. They glow ONLY when she is angry, at 163 nits (RULED BY BARRY 2026-08-04: \"no, glow, only when angry, 163 nits\" - supersedes the earlier wording here, \"four electric-blue glowing eyes\", which read as a permanent state and contradicted the VISUAL CANON entry above)",
        ),
    ]
    merged = live
    for old, new in fixes:
        if old in merged:
            merged = merged.replace(old, new, 1)
        else:
            print(f"  note: glow-ruling fix already applied or wording differs: {old[:48]}...")

    merged = splice(merged)

    # --- write both copies so they can never drift apart again ---
    with open(DISK, "w", encoding="utf-8") as fh:
        fh.write(merged)
    conn.execute("UPDATE facts SET content = ? WHERE id = ?", (merged, FACT_ID))
    conn.commit()

    print(f"disk  {DISK}: {len(open(DISK, encoding='utf-8').read()):,} chars (was 12,475)")
    print(f"fact  {FACT_ID}: {len(merged):,} chars (was {len(live):,})")
    print(f"backups written to {bdir} with suffix {stamp}")


if __name__ == "__main__":
    sys.exit(main())
