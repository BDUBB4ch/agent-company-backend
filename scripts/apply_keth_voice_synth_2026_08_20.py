"""Keth's voice, refined by Barry 2026-08-20: "well make it sound synthesized slightly."

Adds the third term to his lock and CORRECTS a gloss Claude wrote an hour earlier. The
original doubling note said "NOT a robot" as part of explaining SLIGHTLY DOUBLED. That
was Claude's elaboration, not Barry's word, and his new direction moves toward synthetic
-- so the gloss has to be fixed rather than left contradicting him. House rule: his
wording outranks mine, and mine has no standing once his exists.

Updates BOTH copies or neither. Re-runnable: splices by marker.
Written as a script file, never through bash -c.
"""
import pathlib
import sqlite3

REPO = pathlib.Path(__file__).resolve().parent.parent
DISK = REPO / "data" / "barry-character-canon.md"
DB = REPO / "data" / "brain.db"

OLD = """@KETH -- DIRECTED 2026-08-20. HIS WORDS: "higher pitched and slightly doubled."
---------------------------------------------------------------
  LOCK TEXT (paste verbatim into the prompt):
    higher-pitched voice, slightly doubled

  What it means, so it is not "improved" into something else:
    * HIGHER PITCHED -- above a normal adult male register. Not a child, not a
      falsetto, not comic. He is a ~4-foot alien; the pitch belongs to the body.
    * SLIGHTLY DOUBLED -- a second voice layered just under his own, barely
      offset. SLIGHTLY is load-bearing: a subtle alien duality, NOT a chorus, NOT
      a robot, NOT an echo or reverb tail."""

NEW = """@KETH -- DIRECTED 2026-08-20. HIS WORDS, both passes the same day:
  "higher pitched and slightly doubled" + "well make it sound synthesized slightly."
---------------------------------------------------------------
  LOCK TEXT (paste verbatim into the prompt):
    higher-pitched voice, slightly doubled, slightly synthesized

  What it means, so it is not "improved" into something else:
    * HIGHER PITCHED -- above a normal adult male register. Not a child, not a
      falsetto, not comic. He is a ~4-foot alien; the pitch belongs to the body.
    * SLIGHTLY DOUBLED -- a second voice layered just under his own, barely
      offset. A subtle alien duality, not a chorus, not an echo or reverb tail.
    * SLIGHTLY SYNTHESIZED -- a synthetic edge on the voice. Added 2026-08-20.
      ALL THREE TERMS CARRY THE SAME WORD: SLIGHTLY. What he is describing is a
      performance that reads as a person who is not quite human -- an artificial
      sheen over a real delivery. Not a robot, not a vocoder, not autotune, and
      never processed so hard the words get difficult to catch.
      ⚠️ CORRECTION TO THIS FILE'S OWN EARLIER WORDING: the doubling bullet above
      first read "NOT a chorus, NOT a robot, NOT an echo" -- Claude's gloss,
      written before this direction existed. "Not a robot" now reads as arguing
      with him, so it has been narrowed to what he actually ruled out about the
      DOUBLING. A synthetic edge IS wanted. Only the extreme is not."""

MARKER = "SLIGHTLY SYNTHESIZED -- a synthetic edge on the voice"

HOWTO_OLD = """  ⚠️ DOUBLING IS A POST EFFECT AND MAY NOT SURVIVE A TEXT PROMPT."""

HOWTO_NEW = """  ⚠️ DOUBLING AND SYNTHESIS ARE BOTH POST EFFECTS AND MAY NOT SURVIVE A TEXT PROMPT.
  Good news: they are the SAME post chain. Duplicate the take, offset the copy a few
  milliseconds, detune it slightly, and sit it under the original -- that one move
  produces the doubling AND most of the synthetic edge at once. Reach for a light
  chorus or formant shift only if it still reads too human."""


def splice(text: str) -> str | None:
    if MARKER in text:
        return None
    if OLD not in text:
        raise SystemExit("Keth's entry was not found byte-for-byte. Nothing written.")
    if HOWTO_OLD not in text:
        raise SystemExit("the post-effect note was not found. Nothing written.")
    return text.replace(OLD, NEW, 1).replace(HOWTO_OLD, HOWTO_NEW, 1)


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

    bak = REPO / "data" / "backup_disk_canon_before_keth_synth_2026-08-20.md"
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
    for check in (
        "higher-pitched voice, slightly doubled, slightly synthesized",
        "SLIGHTLY SYNTHESIZED -- a synthetic edge on the voice",
        "well make it sound synthesized slightly.",
        "they are the SAME post chain",
    ):
        assert check in after_fact, f"missing after write: {check[:50]}"
    assert "SLIGHTLY is load-bearing: a subtle alien duality, NOT a chorus, NOT" not in after_fact, \
        "the superseded gloss is still live"
    print("verified: three-term lock in place, old gloss corrected, copies in sync")


if __name__ == "__main__":
    main()
