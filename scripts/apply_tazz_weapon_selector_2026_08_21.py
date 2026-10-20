"""@Tazz's-Weapon lethality selector -- Barry, 2026-08-21, his words:
"its part of the tech of the weapon, she can go lethal as well, its just the
push of a button. warheads armed or not."

Appends the ruling to the weapon-pairing table area of the canon (the WHO
CARRIES WHAT section lists her weapon lore). Both copies or neither.
"""
import pathlib
import sqlite3

REPO = pathlib.Path(__file__).resolve().parent.parent
DISK = REPO / "data" / "barry-character-canon.md"
DB = REPO / "data" / "brain.db"

ANCHOR = """  TAZZ    TWO HANDS, ALWAYS."""

NEW = """  TAZZ WEAPON RULING 2026-08-21 -- SELECTABLE LETHALITY. Barry: "its part of
          the tech of the weapon, she can go lethal as well, its just the push
          of a button. warheads armed or not." The mini missile blaster has a
          selector: warheads ARMED (lethal) or SAFED (non-lethal, concussive
          -- bursts that throw bodies, leave targets writhing or out cold,
          nobody dead). One button. Which mode a shot uses is a CHOICE she
          makes on screen -- show the thumb on the selector when it matters.
  TAZZ    TWO HANDS, ALWAYS."""

MARKER = "SELECTABLE LETHALITY"


def main() -> None:
    disk_text = DISK.read_text(encoding="utf-8")
    conn = sqlite3.connect(DB)
    fact_text = conn.execute("SELECT content FROM facts WHERE id = 592").fetchone()[0]
    if disk_text != fact_text:
        raise SystemExit("copies differ -- fix drift first, nothing written.")
    if MARKER in disk_text:
        print("already applied")
        return
    if ANCHOR not in disk_text:
        raise SystemExit("anchor line not found -- nothing written.")

    bak = REPO / "data" / "backup_disk_canon_before_tazz_selector_2026-08-21.md"
    if not bak.exists():
        bak.write_text(disk_text, encoding="utf-8")
    updated = disk_text.replace(ANCHOR, NEW, 1)
    DISK.write_text(updated, encoding="utf-8")
    conn.execute("UPDATE facts SET content = ? WHERE id = 592", (updated,))
    conn.commit()

    after_disk = DISK.read_text(encoding="utf-8")
    after_fact = conn.execute("SELECT content FROM facts WHERE id = 592").fetchone()[0]
    assert after_disk == after_fact and MARKER in after_fact
    print(f"both copies -> {len(disk_text):,} -> {len(updated):,} chars | in sync")


if __name__ == "__main__":
    main()
