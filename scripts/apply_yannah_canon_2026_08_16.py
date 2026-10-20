"""Yannah's NEW CANON -- Barry, 2026-08-16, his words verbatim ("Yannah's new canon").

He supplied a full "Yannah baseline (baked into each)" prompt preamble and called it
canon. It REPLACES the 2026-08-08 anchor line. The old wording is kept on record
inline, labelled SUPERSEDED, exactly as Tazz's weapon change was handled.

Updates BOTH copies (data/barry-character-canon.md + facts.id=592) or neither.
Re-runnable: splices by marker, never stacks. Backs up both first.

Written as a script file, never through bash -c python -c: backticks and quotes get
command-substituted and have silently blanked text out of a fact before.
"""
import pathlib
import sqlite3

REPO = pathlib.Path(__file__).resolve().parent.parent
DISK = REPO / "data" / "barry-character-canon.md"
DB = REPO / "data" / "brain.db"

# The exact 2026-08-08 anchor block being replaced (must match byte-for-byte in both
# copies, so a drifted copy fails loudly instead of being silently half-updated).
OLD_ANCHOR = """@YANNAH: Young alien woman ~19 years old, noticeably pointed ears, green and
brown double-ringed fractal irises -- non-glowing. Subtle gold freckle-like
spots around upper cheeks and outer eye area. Short asymmetrical wavy hair one
side shaved. Grey and black form-fitting tactical jumpsuit with teal piping.
Alien pistol with tech modifications. Forearm bot controller in sleeve."""

# His words. Punctuation normalised to ASCII only (em dash -> --), nothing else touched.
NEW_ANCHOR = """@YANNAH -- BARRY'S NEW CANON, 2026-08-16. HIS WORDS. This is the baseline he
bakes into every Yannah prompt, and it REPLACES the 2026-08-08 anchor line.

Yannah baseline (baked into each): original fictional alien character (not a
real person, not a celebrity, not based on anyone real); a young-adult alien
woman who reads Afro-Latina with warm brown skin; clear, smooth, blemish-free
youthful skin (even complexion, natural fine pores, no acne/spots/scars) with
very faint, barely-noticeable gold freckles ONLY on her cheeks; noticeably
pointed ears; emerald-green-and-brown double-ringed fractal irises -- the
double rings emerald green over a brown iris, non-glowing, natural; a small,
subtle jewel gem stud under her RIGHT eye; short asymmetrical twisted locs /
two-strand twists swept up, dark with warm copper-auburn tips, one side shaved
in an undercut, gold ear cuff on the exposed pointed ear; athletic and lean
build; confident, playful expression. Black fitted tactical jumpsuit with teal
piping, reinforced knees, utility belt, thigh holster rig, compact comms unit
at hip. Hyper-realistic, documentary realism, not CGI/anime, no text or logos.

  SUPERSEDED -- her 2026-08-08 anchor. ON RECORD, DO NOT RENDER FROM:
   "Young alien woman ~19 years old, noticeably pointed ears, green and brown
    double-ringed fractal irises -- non-glowing. Subtle gold freckle-like spots
    around upper cheeks and outer eye area. Short asymmetrical wavy hair one
    side shaved. Grey and black form-fitting tactical jumpsuit with teal
    piping. Alien pistol with tech modifications. Forearm bot controller in
    sleeve."

  STILL CANON, not restated in the baseline and NOT cancelled by it: she is
   ~19; her weapon is @Yannah's-Machine-Pistol (liquid-metal, forest green,
   white variation also hers -- see PROPS and the WHO CARRIES WHAT table); she
   is the same species as Bia and Tazz. The baseline is a LOOK baseline; it
   does not speak to weapons, age or role, so nothing there is overridden."""

MARKER = "*** YANNAH -- NEW CANON. BARRY, 2026-08-16"

NOTE = """

===============================================================
*** YANNAH -- NEW CANON. BARRY, 2026-08-16. HIS WORDS. ***
"Yannah's new canon" -- he supplied the full baseline he bakes into every one of
her prompts. It is now her anchor. The 2026-08-08 wording is kept on record with
the anchor itself, superseded.
===============================================================

WHAT THIS CHANGED, line by line -- so nobody re-promotes an old wording:

  SKIN / HERITAGE  NEW. Reads Afro-Latina, warm brown skin. Clear, smooth,
                   blemish-free youthful skin -- even complexion, natural fine
                   pores, no acne, no scars. Never recorded for her before.

  FRECKLES         SETTLED, third ruling on this. VERY FAINT, barely
                   noticeable, gold, and ONLY on her cheeks. This supersedes
                   the 2026-08-08 "upper cheeks AND outer eye area" and it
                   supersedes the 2026-08-07 "YANNAH HAS NO SPOTS" ruling for
                   good. Both older wordings stay on record elsewhere in this
                   document and must not be re-promoted. Note the older
                   TRAINING-CAPTION sections below still say "NO SPOTS" -- they
                   are older than this and the anchor wins.

  EYES             REFINED, not reversed. Still double-ringed fractal and still
                   NON-GLOWING. Made explicit: the double rings are EMERALD
                   GREEN over a BROWN iris. Read the old "green and brown" that
                   way -- green rings, brown iris, natural.

  FACE JEWELLERY   NEW. A small, subtle jewel gem stud under her RIGHT eye.
                   Right eye specifically -- do not mirror it.

  HAIR             CHANGED. Short asymmetrical TWISTED LOCS / two-strand twists
                   swept up, dark with warm COPPER-AUBURN TIPS, one side shaved
                   in an undercut. Supersedes "short asymmetrical wavy hair one
                   side shaved" -- the asymmetry and the shaved side survive,
                   the texture and the tips are new.

  EARS             Noticeably pointed (unchanged) + NEW: a GOLD EAR CUFF on the
                   exposed pointed ear -- the shaved side, where it shows.

  BUILD / MANNER   NEW in the anchor: athletic and lean build; confident,
                   playful expression.

  JUMPSUIT         CHANGED BACK TO BLACK. "Black fitted tactical jumpsuit with
                   teal piping", plus NEW: reinforced knees, utility belt,
                   thigh holster rig, compact comms unit at hip.
                   *** This REVERSES the 2026-08-08 note in this document that
                   read "BIA / YANNAH TACTICAL SUIT COLOUR -- anchor: GREY AND
                   BLACK ... supersedes the older plain black fitted". For
                   YANNAH the answer is now BLACK FITTED with teal piping. That
                   note still governs BIA, who is unchanged at grey and black.

  RENDER RULES     NEW, carried in his baseline and to be kept in prompts:
                   original fictional alien character -- not a real person, not
                   a celebrity, not based on anyone real; hyper-realistic;
                   documentary realism; NOT CGI, NOT anime; no text, no logos.

NOT RULED ON -- ask him, do not assume:
  * Her FOREARM BOT CONTROLLER in the sleeve. The old anchor had it, the new
    baseline does not mention it. A baseline that lists her rig is the place it
    would appear, so it may be dropped -- but he did not say so. Treat it as
    still canon and ASK before writing a shot that depends on it either way.
  * Her staged Kontext reference tools/ComfyUI/input/yannah_ref.png is from the
    OLD look and was already known to drift. For Kontext THE REFERENCE GOVERNS
    CANON, so it will fight this baseline. It needs replacing with a frame made
    from the new baseline before it is used again.
  * Her trained LoRA was trained on the old look. @Yannah in a LOCAL image
    fence loads those weights, so local renders will lag this canon until she
    is retrained. Higgsfield prompts using the baseline are unaffected.
"""


def splice(text: str, label: str) -> str | None:
    """Return updated text, or None if already applied. Raises if the old anchor is missing."""
    if MARKER in text:
        return None
    if OLD_ANCHOR not in text:
        raise SystemExit(
            f"{label}: the 2026-08-08 @YANNAH anchor was not found byte-for-byte. "
            "Copies have drifted -- resolve by hand, nothing was written."
        )
    return text.replace(OLD_ANCHOR, NEW_ANCHOR, 1) + NOTE


def main() -> None:
    disk_text = DISK.read_text(encoding="utf-8")
    conn = sqlite3.connect(DB)
    row = conn.execute("SELECT content FROM facts WHERE id = 592").fetchone()
    if row is None:
        raise SystemExit("fact 592 not found -- nothing written.")
    fact_text = row[0]

    # Both spliced before either is written, so a drifted copy aborts the whole run.
    new_disk = splice(disk_text, "disk canon")
    new_fact = splice(fact_text, "fact 592")

    if new_disk is None and new_fact is None:
        print("already applied to both copies -- nothing to do")
        return

    bak = REPO / "data" / "backup_disk_canon_before_yannah_canon_2026-08-16.md"
    if not bak.exists():
        bak.write_text(disk_text, encoding="utf-8")
    bak2 = REPO / "data" / "backup_fact592_canon_before_yannah_canon_2026-08-16.md"
    if not bak2.exists():
        bak2.write_text(fact_text, encoding="utf-8")
    print(f"backups: {bak.name}, {bak2.name}")

    if new_disk is not None:
        DISK.write_text(new_disk, encoding="utf-8")
        print(f"disk canon -> {len(disk_text):,} -> {len(new_disk):,} chars")
    else:
        print("disk canon: already applied")

    if new_fact is not None:
        conn.execute("UPDATE facts SET content = ? WHERE id = 592", (new_fact,))
        conn.commit()
        print(f"fact 592   -> {len(fact_text):,} -> {len(new_fact):,} chars")
    else:
        print("fact 592: already applied")

    # Verify by re-reading, not by trusting the write.
    after_disk = DISK.read_text(encoding="utf-8")
    after_fact = conn.execute("SELECT content FROM facts WHERE id = 592").fetchone()[0]
    for label, t in (("disk", after_disk), ("fact 592", after_fact)):
        assert MARKER in t, f"{label}: marker missing after write"
        assert "jewel gem stud under her RIGHT eye" in t, f"{label}: baseline missing"
        assert "gold ear cuff on the exposed pointed ear" in t, f"{label}: ear cuff missing"
        assert "copper-auburn tips" in t, f"{label}: hair missing"
        assert OLD_ANCHOR not in t, f"{label}: old anchor still present as live canon"
        assert "SUPERSEDED -- her 2026-08-08 anchor" in t, f"{label}: old wording not kept"
        print(f"{label}: verified")


if __name__ == "__main__":
    main()
