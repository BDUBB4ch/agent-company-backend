"""CORRECTION -- B Dubb's voice is a CREATED voice, not Barry's own voice.

Barry, 2026-08-20: "its not MY voice, its a voice i created with my voice."

The previous block recorded his "yes" as "B Dubb's voice IS Barry's own voice", which
overshot the answer. His voice was the INPUT to making it; the output is a separate
created asset. That distinction changes the festival conclusion, so the block is
rewritten rather than patched.

Updates BOTH copies or neither. Re-runnable: splices by marker.
Written as a script file, never through bash -c.
"""
import pathlib
import sqlite3

REPO = pathlib.Path(__file__).resolve().parent.parent
DISK = REPO / "data" / "barry-character-canon.md"
DB = REPO / "data" / "brain.db"

MARKER = "B DUBB'S VOICE IS A CREATED VOICE, MADE FROM BARRY'S -- RULED 2026-08-20"

OLD = """  *** B DUBB'S VOICE IS BARRY'S OWN VOICE -- RULED 2026-08-20. ***
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

NEW = """  *** B DUBB'S VOICE IS A CREATED VOICE, MADE FROM BARRY'S -- RULED 2026-08-20. ***
  His words: "its not MY voice, its a voice i created with my voice."
  Open since 2026-08-13; settled. AND IT SETTLES THE SUB-QUESTION TOO -- the
  57-second sample he supplied IS that created voice, not a stock preset.

  READ THE DISTINCTION CAREFULLY, it is the whole ruling:
  His real voice was the INPUT used to make it. The thing that speaks as B Dubb is
  the OUTPUT -- a separate, generated voice asset. It is NOT a recording of Barry
  and it is NOT him performing the line. Do not describe it as "Barry's voice",
  and do not treat a B Dubb line as something he has to go and record.

  WHAT FOLLOWS FROM IT:
  * THE FESTIVAL QUESTION IS NOT SETTLED BY THIS, and the earlier version of this
    block was WRONG to say it was. Higgsfield's rule bars a real person's face or
    voice AS INPUT, including your own. A created voice IS a generated asset --
    but Barry's real voice was the input that produced it, which is exactly what
    the rule names. Whether a derived voice counts is a question for HIGGSFIELD,
    not something to be decided here in either direction. ASK THEM.
    ⚠️ SEPARATELY AND INDEPENDENTLY: B DUBB'S FACE STILL BARS A FESTIVAL ENTRY.
    That has never been in doubt and does not depend on any of the above. So a
    festival piece still cannot contain B Dubb -- the voice ruling simply is not
    the reason.
  * SEEDANCE'S OWN BAN is on "reference images or videos containing real human
    faces". Audio is not named at all, and a created voice is a further step away
    from what the rule covers. Still UNVERIFIED -- test with one throwaway clip
    before relying on it.
  * "CLEANER" IS ABOUT THE RENDER, NOT A RECORDING. Since the voice is generated,
    there is no microphone to fix: cleaner means a better output from the tool
    that makes it -- headroom around -3 dBFS, no clipping. His sample peaks at
    0.0 dBFS with no headroom, which is the measurable fault behind his note.
  * THE VOICE ALREADY EXISTS. It does not need to be created, only re-rendered
    cleaner. On Higgsfield, custom voices live under Voice Preset -- 3 slots per
    account, made from a sample of up to 2 minutes."""


def splice(text: str) -> str | None:
    if MARKER in text:
        return None
    if OLD not in text:
        raise SystemExit("the previous ruling block was not found. Nothing written.")
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

    bak = REPO / "data" / "backup_disk_canon_before_bdubb_voice_correction_2026-08-20.md"
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
    for check in (MARKER, "its not MY voice, its a voice i created with my voice",
                  "THE FESTIVAL QUESTION IS NOT SETTLED BY THIS",
                  "B DUBB'S FACE STILL BARS A FESTIVAL ENTRY",
                  "THE VOICE ALREADY EXISTS"):
        assert check in after_fact, f"missing after write: {check[:50]}"
    assert "B DUBB'S VOICE IS BARRY'S OWN VOICE" not in after_fact, \
        "the wrong ruling is still live"
    assert "ONE SUB-QUESTION NOT ASKED YET" not in after_fact, \
        "the resolved sub-question is still listed as open"
    print("verified: corrected ruling in place, copies in sync")


if __name__ == "__main__":
    main()
