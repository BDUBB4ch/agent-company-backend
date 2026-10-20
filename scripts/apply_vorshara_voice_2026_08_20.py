"""Vor'Shara's voice -- DIRECTED by Barry 2026-08-20, his words:
"i want this voice to sound more gritty and vengefull, for lady vor and a lil deeper"

Fills the @Vorshara slot in the VOICE BIBLE and removes her from the NOT YET DIRECTED
list. Her sample arrived after the other five (hf_20260820_205646...mp3), same audition
line as the alien cast.

Updates BOTH copies or neither. Re-runnable: splices by marker.
Written as a script file, never through bash -c.
"""
import pathlib
import sqlite3

REPO = pathlib.Path(__file__).resolve().parent.parent
DISK = REPO / "data" / "barry-character-canon.md"
DB = REPO / "data" / "brain.db"

MARKER = "@VORSHARA -- DIRECTED 2026-08-20"

OLD_PENDING = """NOT YET DIRECTED -- do not invent these, ask him:
  @B-DUBB-new, @Bia-2, @Tazz, @Yannah, @Vorshara
---------------------------------------------------------------"""

NEW_ENTRY = """---------------------------------------------------------------
@VORSHARA -- DIRECTED 2026-08-20. HIS WORDS: "i want this voice to sound more
gritty and vengefull, for lady vor and a lil deeper."
---------------------------------------------------------------
  LOCK TEXT (paste verbatim into the prompt):
    gritty, vengeful, a little deeper

  What each term is actually asking for -- they are three different levers:
    * GRITTY -- TEXTURE, not pitch. Rasp, grain, a rough edge on the tone. This
      is the one thing pitch adjustment cannot give you; it comes from the voice
      chosen at generation, or from light saturation in post.
    * VENGEFUL -- PERFORMANCE, not a setting. Per the method this office already
      follows: an emotion label produces generic anger. Give the delivery a JOB
      and the intent arrives on its own -- she is not "being vengeful", she is
      deciding what someone's punishment will be while she says the line. Write
      the task, not the adjective.
    * A LITTLE DEEPER -- PITCH. Below her sample. "A LITTLE" is his word: this is
      a shift down, not a register change, and she does not become a low voice.

  Reference sample he supplied: Downloads/hf_20260820_205646_69478da9-28bb-478e-
  b7c6-04716fb16ac4.mp3 (Higgsfield-generated, 4.61s, same audition line as the
  alien cast). MEASURED: median F0 216.2 Hz (A3), p10-p90 156-281 Hz, pitch
  spread 82.5 Hz IQR -- the MOST animated delivery of the six -- RMS -17.6 dBFS,
  peak -4.5. That sample is the BEFORE; the direction above is the correction.

  ⚠️ WHY "A LIL DEEPER" FIXES A REAL PROBLEM, not just a preference: at 216 Hz she
  sits 0.5 SEMITONES FROM TAZZ (222 Hz). They are the same pitch to the ear. In a
  scene where both speak and neither is on camera, they would not be tellable
  apart. Moving her down separates them.

---------------------------------------------------------------
NOT YET DIRECTED -- do not invent these, ask him:
  @B-DUBB-new, @Bia-2, @Tazz, @Yannah
---------------------------------------------------------------"""


def splice(text: str) -> str | None:
    if MARKER in text:
        return None
    if OLD_PENDING not in text:
        raise SystemExit("the NOT YET DIRECTED block was not found. Nothing written.")
    return text.replace(OLD_PENDING, NEW_ENTRY, 1)


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

    bak = REPO / "data" / "backup_disk_canon_before_vorshara_voice_2026-08-20.md"
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
    for check in (MARKER, "gritty, vengeful, a little deeper",
                  "0.5 SEMITONES FROM TAZZ",
                  "@B-DUBB-new, @Bia-2, @Tazz, @Yannah"):
        assert check in after_fact, f"missing after write: {check[:50]}"
    assert "@B-DUBB-new, @Bia-2, @Tazz, @Yannah, @Vorshara" not in after_fact, \
        "Vorshara still listed as undirected"
    print("verified: Vor'Shara entry in place, removed from pending, copies in sync")


if __name__ == "__main__":
    main()
