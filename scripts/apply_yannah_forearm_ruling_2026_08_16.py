"""Yannah's forearm bot controller -- RULED by Barry, 2026-08-16: "na, n forearm thing, Yet"

Asked directly whether the forearm bot controller survived his new baseline (the old
anchor had it, the baseline does not mention it). He said no -- with a "Yet", so this
is a REMOVAL with the door left open, not a deletion of the idea.

Converts the open question left by apply_yannah_canon_2026_08_16.py into a ruling, in
BOTH copies or neither. Re-runnable: splices by marker, never stacks.

Written as a script file, never through bash -c python -c: backticks and quotes get
command-substituted and have silently blanked text out of a fact before.
"""
import pathlib
import sqlite3

REPO = pathlib.Path(__file__).resolve().parent.parent
DISK = REPO / "data" / "barry-character-canon.md"
DB = REPO / "data" / "brain.db"

OLD = """NOT RULED ON -- ask him, do not assume:
  * Her FOREARM BOT CONTROLLER in the sleeve. The old anchor had it, the new
    baseline does not mention it. A baseline that lists her rig is the place it
    would appear, so it may be dropped -- but he did not say so. Treat it as
    still canon and ASK before writing a shot that depends on it either way."""

NEW = """RULED 2026-08-16 -- asked directly, Barry answered: "na, n forearm thing, Yet"

  * NO FOREARM BOT CONTROLLER. It is OFF her canon. Do not put a forearm unit
    in her sleeve, do not describe one, do not render one, and do not write a
    beat that depends on her having one. The 2026-08-08 anchor's "Forearm bot
    controller in sleeve" is SUPERSEDED -- on record with that anchor, never
    rendered from.
  * HER RIG IS EXACTLY WHAT THE BASELINE LISTS and nothing more: utility belt,
    thigh holster rig, compact comms unit at hip.
  * "YET" IS HIS WORD AND IT IS PART OF THE RULING. He left the door open, so
    this is a REMOVAL, not the idea being killed. If it comes back he will say
    so himself -- nobody reinstates it on their own, and nobody treats the
    "yet" as permission to slip it into a shot early.

STILL NOT RULED ON -- ask him, do not assume:"""

MARKER = 'RULED 2026-08-16 -- asked directly, Barry answered: "na, n forearm thing, Yet"'


def splice(text: str, label: str) -> str | None:
    if MARKER in text:
        return None
    if OLD not in text:
        raise SystemExit(
            f"{label}: the open-question block was not found byte-for-byte. "
            "Nothing was written -- resolve by hand."
        )
    return text.replace(OLD, NEW, 1)


def main() -> None:
    disk_text = DISK.read_text(encoding="utf-8")
    conn = sqlite3.connect(DB)
    row = conn.execute("SELECT content FROM facts WHERE id = 592").fetchone()
    if row is None:
        raise SystemExit("fact 592 not found -- nothing written.")
    fact_text = row[0]

    new_disk = splice(disk_text, "disk canon")
    new_fact = splice(fact_text, "fact 592")

    if new_disk is None and new_fact is None:
        print("already applied to both copies -- nothing to do")
        return

    bak = REPO / "data" / "backup_disk_canon_before_yannah_forearm_2026-08-16.md"
    if not bak.exists():
        bak.write_text(disk_text, encoding="utf-8")
    print(f"backup: {bak.name}")

    if new_disk is not None:
        DISK.write_text(new_disk, encoding="utf-8")
        print(f"disk canon -> {len(disk_text):,} -> {len(new_disk):,} chars")
    if new_fact is not None:
        conn.execute("UPDATE facts SET content = ? WHERE id = 592", (new_fact,))
        conn.commit()
        print(f"fact 592   -> {len(fact_text):,} -> {len(new_fact):,} chars")

    after_disk = DISK.read_text(encoding="utf-8")
    after_fact = conn.execute("SELECT content FROM facts WHERE id = 592").fetchone()[0]
    for label, t in (("disk", after_disk), ("fact 592", after_fact)):
        assert MARKER in t, f"{label}: ruling missing after write"
        assert "NO FOREARM BOT CONTROLLER" in t, f"{label}: ruling body missing"
        assert "Treat it as\n    still canon" not in t, f"{label}: old open question still live"
        # the superseded 2026-08-08 anchor must still carry the original wording on record
        assert "Forearm bot controller in\n    sleeve." in t, f"{label}: superseded record lost"
        print(f"{label}: verified")


if __name__ == "__main__":
    main()
