"""Three more voice directions -- Barry, 2026-08-20, his words:
  TAZZ:   "Tazz can go deeper too"
  YANNAH: "Yannah should sound smart but sexy"
  BIA:    "Bia is the leader. she more direct"

Fills their slots in the VOICE BIBLE, leaving only @B-DUBB-new undirected.

NOTE ON BIA: "she is the leader" is NOT a canon change -- the character profile in
this same document already reads "@BIA -- Leader / Infiltrator / Assassin". It is
confirmation, and it is recorded as such rather than as a new ruling.

Updates BOTH copies or neither. Re-runnable: splices by marker.
Written as a script file, never through bash -c.
"""
import pathlib
import sqlite3

REPO = pathlib.Path(__file__).resolve().parent.parent
DISK = REPO / "data" / "barry-character-canon.md"
DB = REPO / "data" / "brain.db"

MARKER = "@TAZZ -- DIRECTED 2026-08-20"

OLD_PENDING = """---------------------------------------------------------------
NOT YET DIRECTED -- do not invent these, ask him:
  @B-DUBB-new, @Bia-2, @Tazz, @Yannah
---------------------------------------------------------------"""

NEW = """---------------------------------------------------------------
@TAZZ -- DIRECTED 2026-08-20. HIS WORDS: "Tazz can go deeper too."
---------------------------------------------------------------
  LOCK TEXT (paste verbatim into the prompt):
    deeper

  Deeper than her sample, which measured 222.2 Hz (A3) -- second highest of the
  alien cast. She is the strongest of them, visibly muscular, and does not feel
  much pain; a low voice belongs to that body. He gave no other term for her, so
  the lock is one word and stays one word until he adds to it.
  ⚠️ EXECUTION: this is the biggest move in the cast. A pitch shift beyond about
  3 semitones sounds processed, so Tazz should be RE-GENERATED on a genuinely
  deeper voice rather than pitched down from the existing sample.

---------------------------------------------------------------
@YANNAH -- DIRECTED 2026-08-20. HIS WORDS: "Yannah should sound smart but sexy."
---------------------------------------------------------------
  LOCK TEXT (paste verbatim into the prompt):
    smart but sexy

  Two qualities held together -- neither one alone is the note:
    * SMART -- precision. Clean articulation, exact word choice, no filler, no
      uptalk. She is Tech / Recon and ~19; she sounds like she knows the answer.
    * SEXY -- warmth and ease, carried in TEXTURE and PACE, not in performance.
      Unhurried, low-effort, a little breath in the tone. His canon note on her
      elsewhere is "confident, playful expression" and that still holds; this is
      not a purr and not a performance of being sexy.
  ⚠️ THIS PULLS AGAINST HER SAMPLE, flagged rather than silently resolved. Hers
  measured the HIGHEST pitch of the cast (254 Hz, B3) and the MOST animated
  delivery (79.7 Hz IQR). High and busy reads young and bright -- closer to cute
  than to what he asked for. "Smart but sexy" usually wants LOWER and SLOWER. So
  either she comes down the pitch ladder, or the quality has to come entirely
  from pace and texture at her current height. HIS CALL, not one to be assumed.

---------------------------------------------------------------
@BIA-2 -- DIRECTED 2026-08-20. HIS WORDS: "Bia is the leader. she more direct."
---------------------------------------------------------------
  LOCK TEXT (paste verbatim into the prompt):
    direct, the leader

  * DIRECT -- no hedging, no trailing off, no filler, no rising question tone at
    the end of a statement. She says the thing and stops. Command register: she
    is used to being answered.
  * NOT A CANON CHANGE. The character profile in this same document already reads
    "@BIA -- Leader / Infiltrator / Assassin". He is confirming her role, not
    assigning a new one, and her existing personality note stands: confident,
    matter-of-fact, slight bravado, military-type confidence.
  HER SAMPLE ALREADY SUPPORTS THIS -- of the six it has the LOWEST alien pitch
  (186 Hz), a tight spread, and only 1.5% silence: the most continuous, least
  hesitant delivery in the set. Directness is the one quality already on tape.
  Change it least.

---------------------------------------------------------------
NOT YET DIRECTED -- do not invent this, ask him:
  @B-DUBB-new
---------------------------------------------------------------
  His sample is 57s of generic corporate script at 89.9 Hz (F#2), flattest
  delivery of the six, clipped to 0.0 dBFS -- a demo read, not an audition on the
  cast's line. Also still unanswered: whether B Dubb's voice is meant to be
  BARRY'S OWN voice, which decides whether a Higgsfield festival entry is even
  possible (their rules bar a real person's voice as input, including your own)."""


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

    bak = REPO / "data" / "backup_disk_canon_before_voice_directions_b_2026-08-20.md"
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
    for check in (MARKER, "@YANNAH -- DIRECTED 2026-08-20", "@BIA-2 -- DIRECTED 2026-08-20",
                  "smart but sexy", "direct, the leader",
                  "NOT YET DIRECTED -- do not invent this, ask him:\n  @B-DUBB-new"):
        assert check in after_fact, f"missing after write: {check[:50]}"
    print("verified: Tazz, Yannah and Bia directed; only B Dubb left; copies in sync")


if __name__ == "__main__":
    main()
