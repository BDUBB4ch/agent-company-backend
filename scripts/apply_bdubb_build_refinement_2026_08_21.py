"""B Dubb's build REFINED -- Barry, 2026-08-21, his words:
"its supposed to be Medium buils, slightly muscular, with a slightly youthful
appearance for his age"

Extends the 2026-08-20 medium-build ruling: medium build + SLIGHTLY MUSCULAR +
slightly youthful appearance for his age. Consistent with his own "aged-down
26-32" and the V7 relaxed-kit "youthful muscular frame" -- this bakes it into
the anchor itself. Applied to BOTH canon copies or neither; superseded wording
kept on record. Deliberately does NOT sweep his story docs -- no instruction to.
"""
import pathlib
import sqlite3

REPO = pathlib.Path(__file__).resolve().parent.parent
DISK = REPO / "data" / "barry-character-canon.md"
DB = REPO / "data" / "brain.db"

OLD = "@B DUBB: MEDIUM-BUILD Black American Indian male, brownish-red skin tone, aged-down"

NEW = """@B DUBB: MEDIUM-BUILD, SLIGHTLY MUSCULAR Black American Indian male with a
slightly youthful appearance for his age, brownish-red skin tone, aged-down"""

MARKER = "SLIGHTLY MUSCULAR Black American Indian male"

NOTE = """

===============================================================
*** B DUBB BUILD REFINED -- 2026-08-21. BARRY'S WORDS. ***
"its supposed to be Medium buils, slightly muscular, with a slightly youthful
appearance for his age"
===============================================================
Extends the 2026-08-20 medium-build ruling (which stands): MEDIUM BUILD,
SLIGHTLY MUSCULAR, with a SLIGHTLY YOUTHFUL appearance for his age. "Slightly"
carries weight both times -- not bodybuilder, not a teenager; a fit man who
reads younger than his salt-and-pepper goatee says he is. This is consistent
with his existing "aged-down 26-32" and the relaxed-kit "youthful muscular
frame" -- now it is anchor text, not scene dressing. Superseded wording, kept
on record: the anchor previously read "MEDIUM-BUILD Black American Indian
male" with no build texture.
"""


def splice(text: str) -> str | None:
    if MARKER in text:
        return None
    if OLD not in text:
        raise SystemExit("anchor line not found byte-for-byte -- nothing written.")
    return text.replace(OLD, NEW, 1) + NOTE


def main() -> None:
    disk_text = DISK.read_text(encoding="utf-8")
    conn = sqlite3.connect(DB)
    fact_text = conn.execute("SELECT content FROM facts WHERE id = 592").fetchone()[0]
    if disk_text != fact_text:
        raise SystemExit("disk and fact 592 differ -- fix drift first, nothing written.")

    updated = splice(disk_text)
    if updated is None:
        print("already applied")
        return

    bak = REPO / "data" / "backup_disk_canon_before_build_refinement_2026-08-21.md"
    if not bak.exists():
        bak.write_text(disk_text, encoding="utf-8")
    DISK.write_text(updated, encoding="utf-8")
    conn.execute("UPDATE facts SET content = ? WHERE id = 592", (updated,))
    conn.commit()

    after_disk = DISK.read_text(encoding="utf-8")
    after_fact = conn.execute("SELECT content FROM facts WHERE id = 592").fetchone()[0]
    assert after_disk == after_fact, "copies drifted during write"
    assert MARKER in after_fact and "slightly youthful appearance for his age" in after_fact
    print(f"both copies -> {len(disk_text):,} -> {len(updated):,} chars | verified in sync")


if __name__ == "__main__":
    main()
