"""THE PITCH LADDER -- approved by Barry 2026-08-20 ("sure").

Six voices were sitting inside 5.4 semitones with two straight collisions (Bia/Keth
1.3 st, Vor'Shara/Tazz 0.5 st). This sets a target pitch per character so the cast is
tellable apart by ear in a scene where nobody is on camera.

THE NUMBERS ARE DERIVED, NOT AUTHORED. Each target follows from (a) his own direction
for that character -- higher / deeper / smart but sexy / the leader -- and (b) the
measured median F0 of the sample he supplied. He approved the ladder before it was
written. The DIRECTIONS remain his words and are unchanged by this.

Method, so the numbers are reproducible: median fundamental frequency over voiced
frames, autocorrelation, 40ms window / 10ms hop, energy + clarity gated.
Script: scripts/analyze_voice_samples_2026_08_20.py

Updates BOTH copies or neither. Re-runnable: splices by marker.
Written as a script file, never through bash -c.
"""
import pathlib
import sqlite3

REPO = pathlib.Path(__file__).resolve().parent.parent
DISK = REPO / "data" / "barry-character-canon.md"
DB = REPO / "data" / "brain.db"

MARKER = "*** THE PITCH LADDER -- SET 2026-08-20"

ANCHOR = """THE FIVE SLOTS a full lock wants: register/timbre, range and dynamics, tempo,
manner and tics, accent/origin. A lock does not need all five to be useful -- what
Barry has said is what it says, and nothing is invented to fill a gap."""

LADDER = ANCHOR + """

---------------------------------------------------------------
*** THE PITCH LADDER -- SET 2026-08-20, approved by Barry ("sure"). ***
---------------------------------------------------------------
THE PROBLEM IT FIXES: all five alien voices were inside 5.4 SEMITONES of each other,
with two pairs effectively identical -- Bia/Keth 1.3 semitones apart, Vor'Shara/Tazz
0.5 apart. In a scene where two of them speak and neither is on camera, those pairs
could not be told apart. His own three corrections (Keth up, Vor'Shara down, Tazz
down) each targeted a real collision before any of this was measured.

  CHARACTER   SAMPLE      TARGET     MOVE      HIS DIRECTION
  @Keth        200 Hz      250 Hz    +3.8 st   higher-pitched, slightly synthesized
  @Yannah      254 Hz      215 Hz    -2.9 st   smart but sexy
  @Bia-2       186 Hz      185 Hz     --       direct, the leader (anchor: hold her)
  @Vorshara    216 Hz      158 Hz    -5.4 st   gritty, vengeful, a little deeper
  @Tazz        222 Hz      135 Hz    -8.6 st   deeper
  @B-DUBB-new   90 Hz       90 Hz     --       clean (only human; correctly lowest)

RESULT: ~2.6 semitones between every neighbour; the alien cast widens from 5.4 to
10.7 semitones. B Dubb sits 7 semitones below Tazz, so the human never blurs into
the crew. KETH IS ALONE AT THE TOP -- he is the only voice going up, which is what
makes his lift safe.

HOW TO EXECUTE EACH ONE -- this matters more than the numbers:
A pitch shift beyond roughly 3 semitones starts sounding processed unless formants
are corrected. So the move size decides the method, and for two of them the
artifacts are actually ON BRIEF:
  @Bia-2      nothing to do.
  @Yannah     post pitch shift. Within the clean range.
  @Keth       shift, and LET THE ARTIFACTS SHOW -- his brief is "slightly
              synthesized", so processing works in his favour.
  @Vorshara   past the clean range, but her brief is "gritty", so processing also
              works for her. Regenerate if credits allow; shifting is acceptable.
  @Tazz       RE-GENERATE ON A GENUINELY DEEPER VOICE. Hers is the biggest move and
              the ONLY one whose brief does not want artifacts -- pitching her down
              8.6 semitones would simply sound broken.

⚠️ PITCH IS THE WEAKEST SEPARATOR YOU HAVE. Texture and pace do more work than
frequency: Yannah is already distinct because she is the most animated delivery,
Bia because she is the steadiest with almost no silence, Vor'Shara will be distinct
because of grit long before she is distinct because of depth. Use the ladder to stop
voices colliding -- do not expect it to give anyone their character. The LOCK does
that.

⚠️ THESE ARE TARGETS, NOT MEASUREMENTS OF ANYTHING THAT EXISTS. Nothing has been
re-generated or shifted yet as of 2026-08-20. Re-run the analysis script after any
regeneration and correct this table -- a stale target is worse than none."""


def splice(text: str) -> str | None:
    if MARKER in text:
        return None
    if ANCHOR not in text:
        raise SystemExit("the VOICES intro anchor was not found. Nothing written.")
    return text.replace(ANCHOR, LADDER, 1)


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

    bak = REPO / "data" / "backup_disk_canon_before_pitch_ladder_2026-08-20.md"
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
    for check in (MARKER, "@Tazz        222 Hz      135 Hz",
                  "RE-GENERATE ON A GENUINELY DEEPER VOICE",
                  "PITCH IS THE WEAKEST SEPARATOR",
                  "THESE ARE TARGETS"):
        assert check in after_fact, f"missing after write: {check[:50]}"
    print("verified: pitch ladder written, copies in sync")


if __name__ == "__main__":
    main()
