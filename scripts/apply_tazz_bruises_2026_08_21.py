"""TAZZ TAKES BRUISES, NOT BULLET WOUNDS -- Barry, 2026-08-21, his words:
"Tazz to have bullets wound, just deep bruises. bruises that hurt but heals over
the next few days. shes hurt but she know sshe will heal"

Adds the ruling to the canon @TAZZ material in BOTH copies. Her anchor already
says "skin highly durable" -- this states what that MEANS under fire.
"""
import pathlib
import sqlite3

REPO = pathlib.Path(__file__).resolve().parent.parent
DISK = REPO / "data" / "barry-character-canon.md"
DB = REPO / "data" / "brain.db"

ANCHOR = """Mutation: unusually strong for her species, does not feel much pain, skin
highly durable."""

NEW = """Mutation: unusually strong for her species, does not feel much pain, skin
highly durable.
  (RULED 2026-08-21, Barry: "Tazz to have bullets wound, just deep bruises.
   bruises that hurt but heals over the next few days. shes hurt but she know
   sshe will heal." WHAT HER DURABLE SKIN MEANS UNDER FIRE: bullets do NOT
   penetrate her -- no entry wounds, no exit wounds, no bleeding from gunfire,
   ever. An impact staggers her and leaves a DEEP BRUISE, purple-black and
   swollen and genuinely painful -- she feels it, she just doesn't lead with
   it. Bruises heal over the NEXT FEW DAYS. She's hurt, and she knows she will
   heal -- that certainty is part of who she is. Rendering rule: never blood
   on Tazz from bullets; bruising yes. This supersedes any older "heals in one
   day" wording and any scene text giving her seeping or bleeding wounds.)"""

MARKER = "WHAT HER DURABLE SKIN MEANS UNDER FIRE"


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
        raise SystemExit("Tazz mutation line not found byte-for-byte -- nothing written.")

    bak = REPO / "data" / "backup_disk_canon_before_tazz_bruises_2026-08-21.md"
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
