"""Teach Elliot voice-over vs on-camera dialogue in Seedance prompts.

MEASURED FAILURE (2026-08-23): asked for SHOT 02/03 prompts, he put B Dubb's
INTERNAL MONOLOGUE -- "He wasn't full of shit." -- into the `{}` channel.
That channel is spoken dialogue and drives lip-sync, and B Dubb's face is in
frame at the crest, so the render would have shown him mouthing a thought.
Barry caught it before spending credits ("its supposed to be voie over
there"). He also emitted `<[]>` for the SFX channel, which is malformed --
the glyph is `<>`.

Appends one section to seedance-prompting, which is PINNED for Elliot, so it
rides on every message rather than waiting on a read_skill that fires ~1% of
the time. Kept in both copies (fact + knowledge/seedance-prompting.md) per
the sync rule. Re-runnable: replaces the section if already present.
"""
import pathlib
import sqlite3
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MARK = "## VOICE-OVER vs ON-CAMERA DIALOGUE"

SECTION = """
## VOICE-OVER vs ON-CAMERA DIALOGUE -- GET THIS RIGHT, IT COSTS CREDITS

THE FOUR AUDIO CHANNELS, EXACT GLYPHS -- copy them character for character:
    ()      background music
    <>      sound effects        <-- NOT <[]>, not <<>>, not [ ]
    {}      SPOKEN DIALOGUE
    [[]]    subtitles  (written as the CJK bracket pair in the official docs)

`{}` IS LIP-SYNC. A line in `{}` makes that character say it OUT LOUD and the
model animates their mouth. Only use it when the character genuinely speaks on
camera in that shot.

A line the script marks INTERNAL, INTERNAL MONOLOGUE or VO is NARRATION OVER
THE PICTURE. It is not dialogue. Putting it in `{}` produces a man alone on a
mountainside mouthing his own thoughts -- a wasted generation.

DEFAULT, and what Barry actually does: keep voice-over OUT of the prompt and
hand it to him separately for post, labelled with the speaker's voice lock:

    VO (@B-DUBB-new, clean voice): "He wasn't full of shit."

Two reasons this is the default. His face is usually in frame, so `{}` risks
the mouth moving. And voice-over gets timed to the cut in the edit -- baking
it into an 8-second clip removes that control.

ONLY if Barry explicitly asks for the VO inside the generation, make the
non-speaking explicit and tell him it is unverified on Higgsfield:

    {} {English, voice-over narration, speaker not visible on camera, no lip movement: "..."}

NEVER silently convert an INTERNAL line into a `{}` dialogue line.

## WHAT BARRY PASTES INTO HIGGSFIELD

The production block -- the "SHOT 02 -- THE CLIMB | 8 sec" header, CAMERA:,
ENVIRONMENT & LIGHTING:, EXPRESSION:, NEG: -- is HIS SCRIPT FORMAT, for the
script. It is not the prompt. Pasting labelled fields into the generator
invites rendered text and confusion.

When he asks for a shot's PROMPT, the ```image``` fence contains only:
  * one flowing description -- subject with @handle and canon details, action,
    camera and lens, environment, lighting, style, grain
  * the `()` music line
  * the `<>` sound-effects line
  * `{}` ONLY for genuine on-camera speech
Then, outside the fence, any VO lines labelled for post as above.

Negatives go in Higgsfield's own negative field, not inside the prompt -- and
per the official guide, negative control is scoped to subtitles and audio
(`no subtitles`, `no BGM`); visual choices are stated positively.
"""


def patch(text: str) -> str:
    if MARK in text:
        head = text[: text.index(MARK)]
        return head.rstrip() + "\n" + SECTION
    return text.rstrip() + "\n" + SECTION


def main() -> None:
    disk = REPO / "knowledge" / "seedance-prompting.md"
    conn = sqlite3.connect(REPO / "data" / "brain.db")
    row = conn.execute(
        "SELECT id, content FROM facts WHERE source_name='seedance-prompting.md' "
        "AND status='active'").fetchone()
    if not row:
        print("seedance-prompting fact not found -- aborting"); return
    fid, content = row

    (REPO / "data" / f"backup_seedance_before_vo_rule_2026-08-23.md").write_text(
        content, encoding="utf-8")

    new = patch(content)
    conn.execute("UPDATE facts SET content=? WHERE id=?", (new, fid))
    conn.commit()
    print(f"fact {fid}: {len(content):,} -> {len(new):,} chars")

    if disk.is_file():
        disk.write_text(patch(disk.read_text(encoding="utf-8")), encoding="utf-8")
        print(f"disk copy updated: {disk.name}")
    else:
        disk.write_text(new, encoding="utf-8")
        print(f"disk copy created: {disk.name}")

    import memory, agents
    pins = agents.pinned_skills_for("movie")
    blk = memory.pinned_skills_block("MovieDirector", pins)
    assert MARK in blk, "rule did not reach Elliot's pinned block"
    print(f"verified: in Elliot's PINNED block ({len(blk):,} chars, pins={len(pins)})")


if __name__ == "__main__":
    main()
