"""Write the confirmed character -> Higgsfield voice map into the canon.

Barry, 2026-08-29: "Daisy was Yannah, Imogen was Tazz and Bia is Tallulah."
Keth and Vor'Shara follow by elimination (John is the only male voice, Keth
the only male character; Marisol is what remains for Vor'Shara, and he is
weighing Nora for that seat).

This closes a hole open since 2026-08-20: he picked the six voices, and
NOTHING recorded which was which -- so no prompt could ever name one.

Canon lives in TWO places and they drift if you touch one (2026-08-08
lesson): fact 592 in the DB and data/barry-character-canon.md on disk.
This writes BOTH and asserts they end byte-identical.

Re-runnable: replaces its own block by delimiter instead of stacking copies.
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
import memory  # noqa: E402

DISK = os.path.join(ROOT, "data", "barry-character-canon.md")
BEGIN = "<!-- BEGIN VOICE ROSTER 2026-08-29 -->"
END = "<!-- END VOICE ROSTER 2026-08-29 -->"

BLOCK = f"""{BEGIN}

## VOICE ROSTER -- WHICH HIGGSFIELD VOICE IS WHICH CHARACTER (Barry, 2026-08-29)

Confirmed by him: "Daisy was Yannah, Imogen was Tazz and Bia is Tallulah."
Keth follows by elimination -- John is the only male voice and Keth the only
male character. VOR'SHARA IS NORA, his pick 2026-08-29 after listening to Nora
against Marisol (which had held that seat by elimination). Nora measures
153.8 Hz against her approved 158 Hz target. Marisol
(75e72cd5-011b-4130-a474-e8b1ab341f04, Minimax speech 2.8 HD) is now UNUSED --
kept on record, not assigned.

He picked these voices on 2026-08-20 and nothing recorded the mapping, so for
nine days the written voice locks were the ONLY way to carry a voice. They are
still the way you DIRECT a performance -- register, emotion, pacing -- but the
voice itself now has a name and an id.

| Character | Voice | Engine | voice_id |
|---|---|---|---|
| @B-DUBB-new | B-Dubb-Voice (HIS OWN, made from his voice) | ElevenLabs -> Higgsfield element | 9b162037-e549-4065-9562-ebac293ee72a |
| @B-DUBB-new FALLBACK | Sterling | preset | dc382508-c8bd-443c-8cb2-46e57b8d2e6f |
| @Bia-2 | Tallulah | ElevenLabs v3 | f32c8f51-449e-4ddf-bdf7-1527e11df917 |
| @Yannah | Daisy | ElevenLabs v3 | 032386ec-491b-5bdc-81ac-49e9a6a2c89d |
| @Tazz | Imogen | Qwen audio 3.0 TTS | 3811e986-0891-47cf-a1f5-78a1d62a547a |
| @Keth | John | ElevenLabs | 6b528d43-c056-4a2f-9d82-1591a7ba13b0 |
| @Vorshara | Nora | preset | d081b915-6623-4a44-bacf-80d0f1c90a03 |

**B DUBB'S VOICE IS HIS OWN AND IT IS NOT A PRESET.** He built it on ElevenLabs
from his own voice, then brought it into Higgsfield as an element. His ruling
on the backup, 2026-08-29: "if my voice dont work, i will use sterlings voice."
Measured: Sterling 91.4 Hz against his B Dubb at 90.4 Hz, one hertz apart, with
a canon target of 90 -- he chose that by ear.

**RULES**
- Name the voice, do not describe it, when a generation can take one.
- The written voice locks STAY. A voice id carries timbre; it does not carry
  Vor'Shara being stern toward B Dubb, or Yannah being the most animated of
  them, or Bia being the steadiest. Direction is still written.
- Never identify a voice by pitch. Claude tried it here and got ONE of five
  right (Keth, and that came from gender, not pitch). Preset preview clips
  speak different text at different energy, so their median pitch drifts
  30-70 Hz off a real generated line -- Bia's own sample measures 190.5 Hz
  while Tallulah's preview measures 150.9. Ask Barry; record the answer.

{END}"""


def splice(text):
    if BEGIN in text and END in text:
        head = text.split(BEGIN)[0]
        tail = text.split(END)[1]
        return head + BLOCK + tail
    return text.rstrip() + "\n\n" + BLOCK + "\n"


def main():
    disk = open(DISK, encoding="utf-8").read()
    new_disk = splice(disk)
    assert BEGIN in new_disk and new_disk.count(BEGIN) == 1
    with open(DISK, "w", encoding="utf-8") as fh:
        fh.write(new_disk)

    with memory.get_db() as conn:
        row = conn.execute(
            "SELECT id, content FROM facts WHERE id=592").fetchone()
        assert row, "fact 592 (canon) not found"
        new_fact = splice(row["content"])
        assert new_fact.count(BEGIN) == 1
        conn.execute("UPDATE facts SET content=? WHERE id=592", (new_fact,))

    with memory.get_db() as conn:
        stored = conn.execute(
            "SELECT content FROM facts WHERE id=592").fetchone()[0]
    on_disk = open(DISK, encoding="utf-8").read()
    print(f"disk  {len(disk):,} -> {len(on_disk):,}")
    print(f"fact  {len(row['content']):,} -> {len(stored):,}")
    assert "Tallulah" in stored and "Tallulah" in on_disk, "roster missing"
    assert stored == on_disk, "DRIFT: fact 592 and disk copy differ"
    print("VERIFIED: roster in both copies, and they are byte-identical.")


if __name__ == "__main__":
    main()
