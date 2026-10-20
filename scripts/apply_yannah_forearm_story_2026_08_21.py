"""Yannah's forearm controller -- the "Yet" RESOLVED as a story beat.

Barry, 2026-08-21: "that arm thing for Yannah comes later, Keth helps her with it."

The 2026-08-16 removal stands for her CURRENT look; what's new is WHY: it is a
future story beat -- she gets the forearm unit later in the series, and Keth helps
her with it. Updates the ruling block in BOTH canon copies or neither.
"""
import pathlib
import sqlite3

REPO = pathlib.Path(__file__).resolve().parent.parent
DISK = REPO / "data" / "barry-character-canon.md"
DB = REPO / "data" / "brain.db"

OLD = """  * "YET" IS HIS WORD AND IT IS PART OF THE RULING. He left the door open, so
    this is a REMOVAL, not the idea being killed. If it comes back he will say
    so himself -- nobody reinstates it on their own, and nobody treats the
    "yet" as permission to slip it into a shot early."""

NEW = """  * "YET" RESOLVED 2026-08-21 -- IT IS A STORY BEAT. Barry: "that arm thing
    for Yannah comes later, Keth helps her with it." So the forearm bot
    controller EXISTS in the series' future: Yannah gets it LATER, and KETH
    HELPS HER WITH IT -- the engineer who spent forty years building things,
    building something for the one who helped free him. TIMELINE RULE: in EP1
    and until the story reaches that beat, she has NO forearm unit -- her rig
    is the baseline (utility belt, thigh holster rig, comms unit at hip). Any
    old text showing her using a forearm controller during EP1 predates this
    timeline and is not rendered from. When the story arrives at the beat,
    Barry writes it -- nobody stages it early."""

MARKER = "IT IS A STORY BEAT"


def main() -> None:
    disk_text = DISK.read_text(encoding="utf-8")
    conn = sqlite3.connect(DB)
    fact_text = conn.execute("SELECT content FROM facts WHERE id = 592").fetchone()[0]
    if disk_text != fact_text:
        raise SystemExit("copies differ -- fix drift first, nothing written.")
    if MARKER in disk_text:
        print("already applied")
        return
    if OLD not in disk_text:
        raise SystemExit("ruling block not found byte-for-byte -- nothing written.")

    bak = REPO / "data" / "backup_disk_canon_before_forearm_story_2026-08-21.md"
    if not bak.exists():
        bak.write_text(disk_text, encoding="utf-8")
    updated = disk_text.replace(OLD, NEW, 1)
    DISK.write_text(updated, encoding="utf-8")
    conn.execute("UPDATE facts SET content = ? WHERE id = 592", (updated,))
    conn.commit()

    after_disk = DISK.read_text(encoding="utf-8")
    after_fact = conn.execute("SELECT content FROM facts WHERE id = 592").fetchone()[0]
    assert after_disk == after_fact and MARKER in after_fact
    print(f"both copies -> {len(disk_text):,} -> {len(updated):,} chars | in sync")


if __name__ == "__main__":
    main()
