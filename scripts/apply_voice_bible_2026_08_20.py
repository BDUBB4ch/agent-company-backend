"""VOICE BIBLE -- starts the VOICES section in canon, 2026-08-20.

Barry's voice direction, in HIS words, one character at a time as he gives it. The
section exists because Higgsfield does not expose Seedance 2.5's reference_audio slot,
so the WRITTEN voice lock is the only thing holding a voice across shots.

RULE FOR THIS FILE: only Barry's words describe a voice. Where he has not spoken, the
entry says NOT YET DIRECTED -- it does not get filled in with a guess. Adding a
character means adding to VOICES below and re-running; it splices by marker.

First entry: KETH -- "higher pitched and slightly doubled" (2026-08-20).

Updates BOTH copies or neither. Written as a script file, never through bash -c.
"""
import pathlib
import sqlite3

REPO = pathlib.Path(__file__).resolve().parent.parent
DISK = REPO / "data" / "barry-character-canon.md"
DB = REPO / "data" / "brain.db"

MARKER = "*** VOICES -- THE VOICE BIBLE. BARRY'S WORDS. ***"

SECTION = """

===============================================================
*** VOICES -- THE VOICE BIBLE. BARRY'S WORDS. ***
Started 2026-08-20. A voice drifts between clips unless it is pinned in writing.
===============================================================

WHY THIS EXISTS, and why it is written and not uploaded:
Seedance 2.5 DOES support an audio reference (content.role = reference_audio, 10
clips, 30s total, wav/mp3, addressed as @Audio 1). HIGGSFIELD DOES NOT EXPOSE IT --
Barry tried on 2026-08-20 and the Elements panel would not take a voice, and their
own 2.5 page describes audio only as generated, never as an input. So on Higgsfield
the WRITTEN LOCK carries the voice, alone.

HOW A LOCK IS USED -- the ONEIRIC rule this office already follows:
Paste the lock into EVERY generation VERBATIM, never even a synonym changed. A voice
descriptor written fresh each time is a voice that drifts each time. Dialogue itself
goes in { } and, per the official ByteDance guidance, names its language first:
  {English: "Sometimes life just brings some crazy ass shit."}

THE FIVE SLOTS a full lock wants: register/timbre, range and dynamics, tempo,
manner and tics, accent/origin. A lock does not need all five to be useful -- what
Barry has said is what it says, and nothing is invented to fill a gap.

---------------------------------------------------------------
@KETH -- DIRECTED 2026-08-20. HIS WORDS: "higher pitched and slightly doubled."
---------------------------------------------------------------
  LOCK TEXT (paste verbatim into the prompt):
    higher-pitched voice, slightly doubled

  What it means, so it is not "improved" into something else:
    * HIGHER PITCHED -- above a normal adult male register. Not a child, not a
      falsetto, not comic. He is a ~4-foot alien; the pitch belongs to the body.
    * SLIGHTLY DOUBLED -- a second voice layered just under his own, barely
      offset. SLIGHTLY is load-bearing: a subtle alien duality, NOT a chorus, NOT
      a robot, NOT an echo or reverb tail.
  ⚠️ DOUBLING IS A POST EFFECT AND MAY NOT SURVIVE A TEXT PROMPT. Asking a video
  model for a layered voice in words is unreliable. If a generation comes back
  single-tracked, the doubling is added afterwards in the audio tool -- the same
  principle as the anamorphic lesson, only in the other direction: what the video
  model will not hold, move one step LATER into post rather than fighting the
  prompt for it. Say the lock anyway; treat post as the guarantee.

  Reference sample he supplied: Downloads/Keth Voice.mp3 (3.55s, -16.2 dBFS mean,
  -2.3 peak, line "Sometimes life just brings some crazy ass shit."). That sample
  is the BEFORE -- the direction above is the correction to it.

---------------------------------------------------------------
NOT YET DIRECTED -- do not invent these, ask him:
  @B-DUBB-new, @Bia-2, @Tazz, @Yannah, @Vorshara
---------------------------------------------------------------
  He supplied audition samples for B Dubb, Bia, Tazz and Yannah on 2026-08-20 and
  has not yet said what to change about them. NOTHING in this office can hear a
  voice -- Whisper transcribes words only, and no audio-understanding model is
  installed -- so a description of how any of them SOUNDS can only come from him.
  Until he speaks, these entries stay empty. An invented voice is exactly the kind
  of Claude-authored canon he ruled out on 2026-08-08.

  THE AUDITION LINE, worth keeping: he used one identical line for all four alien
  samples -- "Sometimes life just brings some crazy ass shit." Same script,
  different voice, is a true A/B. Reuse it for every future voice test.
  NOTE: Vor'Shara has no sample yet, and B Dubb's sample is 57s -- over Seedance's
  30s single-clip ceiling, so it needs a trim before it could ever be used as a
  reference. His also peaks at 0.0 dBFS (slammed to the ceiling); the four alien
  clips sit at a healthy -0.4 to -2.3.
"""


def splice(text: str, label: str) -> str | None:
    if MARKER in text:
        return None
    return text + SECTION


def main() -> None:
    disk_text = DISK.read_text(encoding="utf-8")
    conn = sqlite3.connect(DB)
    row = conn.execute("SELECT content FROM facts WHERE id = 592").fetchone()
    if row is None:
        raise SystemExit("fact 592 not found -- nothing written.")
    fact_text = row[0]

    if disk_text != fact_text:
        raise SystemExit(
            f"disk ({len(disk_text):,}) and fact 592 ({len(fact_text):,}) already differ. "
            "Nothing written -- resolve the drift first."
        )

    new_disk = splice(disk_text, "disk canon")
    new_fact = splice(fact_text, "fact 592")
    if new_disk is None and new_fact is None:
        print("VOICES section already present -- edit SECTION and change MARKER to extend")
        return

    bak = REPO / "data" / "backup_disk_canon_before_voice_bible_2026-08-20.md"
    if not bak.exists():
        bak.write_text(disk_text, encoding="utf-8")
    print(f"backup: {bak.name}")

    DISK.write_text(new_disk, encoding="utf-8")
    conn.execute("UPDATE facts SET content = ? WHERE id = 592", (new_fact,))
    conn.commit()
    print(f"both copies -> {len(disk_text):,} -> {len(new_disk):,} chars")

    after_disk = DISK.read_text(encoding="utf-8")
    after_fact = conn.execute("SELECT content FROM facts WHERE id = 592").fetchone()[0]
    assert after_disk == after_fact, "copies drifted during the write"
    for check in (MARKER, "higher-pitched voice, slightly doubled",
                  "NOT YET DIRECTED", "SLIGHTLY is load-bearing"):
        assert check in after_fact, f"missing after write: {check[:50]}"
    print("verified: VOICES section present, copies in sync")


if __name__ == "__main__":
    main()
