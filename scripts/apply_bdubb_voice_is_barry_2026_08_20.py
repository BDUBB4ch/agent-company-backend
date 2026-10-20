"""B DUBB'S VOICE IS BARRY'S OWN VOICE -- ruled by Barry 2026-08-20.

Asked directly ("is B Dubb's voice meant to be your own voice?"), he answered: "yes".

This resolves a question open since 2026-08-13 and it decides the Higgsfield Global
Film Festival question, so it is recorded with its consequence attached rather than
as a bare fact.

Updates BOTH copies or neither. Re-runnable: splices by marker.
Written as a script file, never through bash -c.
"""
import pathlib
import sqlite3

REPO = pathlib.Path(__file__).resolve().parent.parent
DISK = REPO / "data" / "barry-character-canon.md"
DB = REPO / "data" / "brain.db"

MARKER = "B DUBB'S VOICE IS BARRY'S OWN VOICE -- RULED 2026-08-20"

OLD = """  ⚠️ STILL UNANSWERED, and it is not a detail: IS B DUBB'S VOICE MEANT TO BE
  BARRY'S OWN VOICE? He plays the character and the character is him. If the
  answer is yes, a Higgsfield Global Film Festival entry is impossible -- their
  rules bar a real person's voice as input, INCLUDING YOUR OWN, the same rule
  that already bars his face. Ask before building anything that depends on it."""

NEW = """  *** B DUBB'S VOICE IS BARRY'S OWN VOICE -- RULED 2026-08-20. ***
  Asked directly, he answered "yes". B Dubb is him: his face, and now explicitly
  his voice. Open since 2026-08-13; settled.

  WHAT FOLLOWS FROM IT:
  * THE HIGGSFIELD GLOBAL FILM FESTIVAL IS OUT for anything with B Dubb in it.
    Their rules bar a real person's face OR voice as input, INCLUDING YOUR OWN.
    His face already barred it; the voice ruling closes the second door. This is
    not new damage -- it was already true -- but it is now certain, and no plan
    should be built assuming a workaround exists. If he ever wants to enter, it
    has to be a piece with no B Dubb in it at all.
  * SEEDANCE ITSELF IS A DIFFERENT QUESTION and is NOT closed. Its documented
    ban is on "reference images or videos containing real human faces" -- audio
    is not named in that rule. So a real voice may be usable as audio input where
    a real face is not. UNVERIFIED; test with one throwaway clip before relying
    on it, and do not state it as fact until it has been tried.
  * "CLEANER" IS THEREFORE ABOUT CAPTURE, NOT CASTING. His voice is the voice; the
    note is about the quality of the recording or the clone output, which the
    measurement supports -- his sample peaks at 0.0 dBFS with no headroom.
  * VOICE CLONING IS THE MECHANISM on Higgsfield: the Audio tab clones a voice
    from a short sample with consent, 3 custom voices per account, up to a
    2-minute wav/mp3 sample, saved under Voice Preset for reuse.

  ⚠️ ONE SUB-QUESTION NOT ASKED YET: is the 57-second sample he supplied already
  HIS CLONED VOICE, or a stock preset that sounds like him? It reads as a demo
  script rather than him talking. That decides whether the clone already exists
  and only needs a cleaner render, or whether it still has to be made. ASK."""


def splice(text: str) -> str | None:
    if MARKER in text:
        return None
    if OLD not in text:
        raise SystemExit("the open-question block was not found. Nothing written.")
    return text.replace(OLD, NEW, 1)


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

    bak = REPO / "data" / "backup_disk_canon_before_bdubb_voice_ruling_2026-08-20.md"
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
    for check in (MARKER, "THE HIGGSFIELD GLOBAL FILM FESTIVAL IS OUT",
                  "SEEDANCE ITSELF IS A DIFFERENT QUESTION",
                  "ONE SUB-QUESTION NOT ASKED YET"):
        assert check in after_fact, f"missing after write: {check[:50]}"
    assert "STILL UNANSWERED, and it is not a detail" not in after_fact, \
        "the open question is still live"
    print("verified: ruling recorded with consequences, copies in sync")


if __name__ == "__main__":
    main()
