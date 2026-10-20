"""Keth's voice, third pass the same day -- Barry: "removed the doubled part."

DOUBLING IS OUT. His lock becomes two terms: higher-pitched, slightly synthesized.
The doubling wording is kept on record as SUPERSEDED, per the house rule that his
superseded wordings are never deleted.

Updates BOTH copies or neither. Re-runnable: splices by marker.
Written as a script file, never through bash -c.
"""
import pathlib
import sqlite3

REPO = pathlib.Path(__file__).resolve().parent.parent
DISK = REPO / "data" / "barry-character-canon.md"
DB = REPO / "data" / "brain.db"

OLD_LOCK = """  LOCK TEXT (paste verbatim into the prompt):
    higher-pitched voice, slightly doubled, slightly synthesized"""

NEW_LOCK = """  LOCK TEXT (paste verbatim into the prompt):
    higher-pitched voice, slightly synthesized

  *** DOUBLING WAS REMOVED 2026-08-20 -- Barry: "removed the doubled part." ***
  He gave it, then took it back the same day. There is NO doubling on Keth: do not
  layer a second voice under his own, and do not let "synthesized" quietly become
  doubling by another name. The superseded wording is kept below, as his superseded
  wordings always are -- on record, never rendered from."""

OLD_BULLET = """    * SLIGHTLY DOUBLED -- a second voice layered just under his own, barely
      offset. A subtle alien duality, not a chorus, not an echo or reverb tail."""

NEW_BULLET = """    * SUPERSEDED -- SLIGHTLY DOUBLED. DO NOT USE. His wording while it stood:
      "a second voice layered just under his own, barely offset. A subtle alien
      duality, not a chorus, not an echo or reverb tail." Removed 2026-08-20."""

OLD_HOWTO = """  ⚠️ DOUBLING AND SYNTHESIS ARE BOTH POST EFFECTS AND MAY NOT SURVIVE A TEXT PROMPT.
  Good news: they are the SAME post chain. Duplicate the take, offset the copy a few
  milliseconds, detune it slightly, and sit it under the original -- that one move
  produces the doubling AND most of the synthetic edge at once. Reach for a light
  chorus or formant shift only if it still reads too human."""

NEW_HOWTO = """  ⚠️ SYNTHESIS IS A POST EFFECT AND MAY NOT SURVIVE A TEXT PROMPT. Say the lock in
  the prompt anyway, and treat post as the guarantee. With doubling removed, the
  reliable move is NOT layering -- it is a light formant shift or a gentle
  chorus/detune at low mix on the single take. Keep the take single-tracked."""

MARKER = 'DOUBLING WAS REMOVED 2026-08-20'


def splice(text: str) -> str | None:
    if MARKER in text:
        return None
    for needle, what in ((OLD_LOCK, "lock text"), (OLD_BULLET, "doubling bullet"),
                         (OLD_HOWTO, "post-effect note")):
        if needle not in text:
            raise SystemExit(f"{what} not found byte-for-byte. Nothing written.")
    return (text.replace(OLD_LOCK, NEW_LOCK, 1)
                .replace(OLD_BULLET, NEW_BULLET, 1)
                .replace(OLD_HOWTO, NEW_HOWTO, 1))


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

    bak = REPO / "data" / "backup_disk_canon_before_keth_undouble_2026-08-20.md"
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
    assert "higher-pitched voice, slightly synthesized" in after_fact
    assert "higher-pitched voice, slightly doubled, slightly synthesized" not in after_fact, \
        "the doubled lock text is still live"
    assert "SUPERSEDED -- SLIGHTLY DOUBLED" in after_fact, "superseded record lost"
    assert MARKER in after_fact
    print("verified: doubling removed, kept on record, copies in sync")


if __name__ == "__main__":
    main()
