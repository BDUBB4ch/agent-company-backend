"""B Dubb's voice -- DIRECTED by Barry 2026-08-20: "B dubb voice audio should be cleaner."

Completes the VOICE BIBLE: all six characters now directed, none left to invent.

Updates BOTH copies or neither. Re-runnable: splices by marker.
Written as a script file, never through bash -c.
"""
import pathlib
import sqlite3

REPO = pathlib.Path(__file__).resolve().parent.parent
DISK = REPO / "data" / "barry-character-canon.md"
DB = REPO / "data" / "brain.db"

MARKER = "@B-DUBB-new -- DIRECTED 2026-08-20"

OLD_PENDING = """---------------------------------------------------------------
NOT YET DIRECTED -- do not invent this, ask him:
  @B-DUBB-new
---------------------------------------------------------------
  His sample is 57s of generic corporate script at 89.9 Hz (F#2), flattest
  delivery of the six, clipped to 0.0 dBFS -- a demo read, not an audition on the
  cast's line. Also still unanswered: whether B Dubb's voice is meant to be
  BARRY'S OWN voice, which decides whether a Higgsfield festival entry is even
  possible (their rules bar a real person's voice as input, including your own)."""

NEW = """---------------------------------------------------------------
@B-DUBB-new -- DIRECTED 2026-08-20. HIS WORDS: "B dubb voice audio should be
cleaner."
---------------------------------------------------------------
  LOCK TEXT (paste verbatim into the prompt):
    clean

  This one is about AUDIO QUALITY, not character -- and the measurement agrees
  with him. His sample is the only one of the six with a real technical fault:
  it PEAKS AT 0.0 dBFS, i.e. slammed into the ceiling with no headroom, which is
  what produces a hard, brittle edge on the loud words. The alien clips all sit
  at a healthy -0.4 to -2.3 peak.
  WHAT CLEAN MEANS HERE: headroom (peak around -3 dBFS, never 0.0), no clipping,
  no crunch on the loud syllables, no room noise or hiss under the quiet ones.
  ⚠️ IF HE MEANT THE DELIVERY RATHER THAN THE FILE -- cleaner diction, less
  mumble -- that reading is not excluded and has not been checked with him. The
  file fault is real and measurable either way, so fix that first and ask if it
  still is not what he wants.

  Reference sample: Downloads/B dub Voice sample.mp3. MEASURED: 57.1s, median F0
  89.9 Hz (F#2) -- by far the lowest voice in the cast and correctly so, he is
  the only human -- p10-p90 78-219 Hz, pitch spread 25.6 Hz IQR (the FLATTEST
  delivery of the six), RMS -20.6 dBFS, peak 0.0, 38.9% silence.
  ⚠️ IT IS NOT AN AUDITION. Unlike the other five it is a 57-second generic
  corporate read ("progress beats polish...") rather than the cast's audition
  line. It is also OVER SEEDANCE'S 30-SECOND SINGLE-CLIP CEILING, so it could
  never be used as a reference_audio asset without a trim.

  ⚠️ STILL UNANSWERED, and it is not a detail: IS B DUBB'S VOICE MEANT TO BE
  BARRY'S OWN VOICE? He plays the character and the character is him. If the
  answer is yes, a Higgsfield Global Film Festival entry is impossible -- their
  rules bar a real person's voice as input, INCLUDING YOUR OWN, the same rule
  that already bars his face. Ask before building anything that depends on it.

---------------------------------------------------------------
ALL SIX DIRECTED as of 2026-08-20. Nothing in this section is invented; every
lock is his wording. If a voice needs a quality nobody has named yet, ASK -- do
not fill the gap.
---------------------------------------------------------------"""


def splice(text: str) -> str | None:
    if MARKER in text:
        return None
    if OLD_PENDING not in text:
        raise SystemExit("the NOT YET DIRECTED block was not found. Nothing written.")
    return text.replace(OLD_PENDING, NEW, 1)


def main() -> None:
    disk_text = DISK.read_text(encoding="utf-8")
    conn = sqlite3.connect(DB)
    fact_text = conn.execute("SELECT content FROM facts WHERE id = 592").fetchone()[0]
    if disk_text != fact_text:
        raise SystemExit("disk and fact 592 differ. Nothing written -- fix the drift first.")

    updated = splice(disk_text)
    if updated is None:
        print("already applied -- nothing to do")
        return

    bak = REPO / "data" / "backup_disk_canon_before_bdubb_voice_2026-08-20.md"
    if not bak.exists():
        bak.write_text(disk_text, encoding="utf-8")
    print(f"backup: {bak.name}")

    DISK.write_text(updated, encoding="utf-8")
    conn.execute("UPDATE facts SET content = ? WHERE id = 592", (updated,))
    conn.commit()
    print(f"both copies -> {len(disk_text):,} -> {len(updated):,} chars")

    after_disk = DISK.read_text(encoding="utf-8")
    after_fact = conn.execute("SELECT content FROM facts WHERE id = 592").fetchone()[0]
    assert after_disk == after_fact, "copies drifted during the write"
    for check in (MARKER, "ALL SIX DIRECTED as of 2026-08-20",
                  "IS B DUBB'S VOICE MEANT TO BE"):
        assert check in after_fact, f"missing after write: {check[:50]}"
    assert "NOT YET DIRECTED" not in after_fact, "a pending block is still present"
    print("verified: all six directed, copies in sync")


if __name__ == "__main__":
    main()
