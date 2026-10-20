"""Mark the pitch ladder SUPERSEDED -- Barry retired it 2026-08-29.

His words: "im not worried about pitch no more, that was befor i found these
voices."

Why it is retired rather than deleted (house rule: superseded wording stays on
record): the ladder existed to solve ONE problem -- all five alien voices sat
inside 5.4 semitones of each other, two pairs nearly identical. He has since
chosen six genuinely distinct voices from four different TTS engines, so the
problem the ladder was built for no longer exists. The targets themselves were
never applied to anything.

Writes BOTH canon copies and asserts they end byte-identical (2026-08-08 rule).
Re-runnable: the marker makes a second run a no-op.
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
import memory  # noqa: E402

DISK = os.path.join(ROOT, "data", "barry-character-canon.md")

OLD = "*** THE PITCH LADDER -- SET 2026-08-20, approved by Barry (\"sure\"). ***"
NEW = (
    "*** THE PITCH LADDER -- SUPERSEDED 2026-08-29. DO NOT APPLY. ***\n"
    "*** Barry: \"im not worried about pitch no more, that was befor i found ***\n"
    "*** these voices.\" The ladder solved ONE problem -- five alien voices    ***\n"
    "*** inside 5.4 semitones, two pairs nearly identical. He has since       ***\n"
    "*** chosen six DISTINCT voices across four TTS engines (see the VOICE    ***\n"
    "*** ROSTER block), so that problem is gone. The targets below were never ***\n"
    "*** applied and are kept only as a record of the reasoning. Separation   ***\n"
    "*** now comes from voice CHOICE, not from shifting pitch.                ***\n"
    "*** Original header: SET 2026-08-20, approved by Barry (\"sure\"). ***"
)


def main():
    disk = open(DISK, encoding="utf-8").read()
    if "SUPERSEDED 2026-08-29. DO NOT APPLY" in disk:
        print("already superseded -- no-op")
        return
    assert disk.count(OLD) == 1, f"anchor found {disk.count(OLD)} times on disk"
    new_disk = disk.replace(OLD, NEW, 1)
    with open(DISK, "w", encoding="utf-8") as fh:
        fh.write(new_disk)

    with memory.get_db() as conn:
        row = conn.execute("SELECT content FROM facts WHERE id=592").fetchone()
        assert row, "fact 592 not found"
        assert row["content"].count(OLD) == 1, "anchor not once in fact 592"
        conn.execute("UPDATE facts SET content=? WHERE id=592",
                     (row["content"].replace(OLD, NEW, 1),))

    with memory.get_db() as conn:
        stored = conn.execute(
            "SELECT content FROM facts WHERE id=592").fetchone()[0]
    on_disk = open(DISK, encoding="utf-8").read()
    assert "SUPERSEDED 2026-08-29. DO NOT APPLY" in stored
    assert stored == on_disk, "DRIFT: fact 592 and disk copy differ"
    print(f"pitch ladder superseded in both copies ({len(disk):,} -> "
          f"{len(on_disk):,}); targets kept on record, byte-identical.")


if __name__ == "__main__":
    main()
