"""B Dubb's build -- RULED by Barry, 2026-08-20: "my character B dubb is supposed to be
medium build not stocky."

Changes STOCKY -> MEDIUM BUILD in both canon copies, in the two places the canon doc says
it: his 2026-08-08 anchor line and the B DUBB character-profile Build line. Old wording is
kept on record inline, never deleted.

Deliberately does NOT touch his own authored story docs (talia-crew-brain-dump,
ep1-scene-anchors, ep1-production-script, the series bible), which also say "stocky".
His 2026-08-14 ruling governs those: SUBSTITUTE IN THE PROMPT, NEVER EDIT THE SCRIPT.

Updates BOTH copies or neither. Re-runnable: splices by marker, never stacks.

Written as a script file, never through bash -c python -c: backticks and quotes get
command-substituted and have silently blanked text out of a fact before.
"""
import pathlib
import sqlite3

REPO = pathlib.Path(__file__).resolve().parent.parent
DISK = REPO / "data" / "barry-character-canon.md"
DB = REPO / "data" / "brain.db"

OLD_ANCHOR = """@B DUBB: Stocky Black American Indian male, brownish-red skin tone, aged-down"""

NEW_ANCHOR = """@B DUBB: MEDIUM-BUILD Black American Indian male, brownish-red skin tone, aged-down"""

OLD_BUILD = """* Build: Stocky, Black American Indian male, brownish-red skin tone, fuller rounded salt-and-pepper goatee"""

NEW_BUILD = """* Build: MEDIUM BUILD, Black American Indian male, brownish-red skin tone, fuller rounded salt-and-pepper goatee
  (Barry, 2026-08-20: "my character B dubb is supposed to be medium build not stocky."
   SUPERSEDED WORDING, kept on record: "Build: Stocky". Nothing else about him changed.)"""

MARKER = 'B DUBB BUILD -- RULED 2026-08-20'

NOTE = """

===============================================================
*** B DUBB BUILD -- RULED 2026-08-20. BARRY'S WORDS. ***
"my character B dubb is supposed to be medium build not stocky"
===============================================================

HE IS MEDIUM BUILD. Not stocky, not heavy-set, not thick, not broad-built, not
bulky, not burly. Write MEDIUM BUILD and nothing heavier.

  * His 2026-08-08 anchor said "Stocky Black American Indian male". That single
    word is SUPERSEDED -- the anchor line above now reads MEDIUM-BUILD. The old
    wording stays on record here and must never be re-promoted from an older
    file, an older render or an older prompt.
  * NOTHING ELSE ABOUT HIM CHANGED. Brownish-red skin tone, aged-down 26-32,
    fuller rounded salt-and-pepper goatee, all-black tactical gear, the black
    vest over the hoodie, the gold number 4 pendant, the Glock .40 -- all
    untouched.
  * WATCH THE SYNONYM DRIFT. "Stocky" leaks back in as "broad", "solid",
    "thick-set", "powerfully built" or "heavy frame". Those are the same
    ruling being broken with a different word. Medium build.

⚠️ HIS OWN STORY DOCUMENTS STILL SAY "STOCKY" and are NOT to be edited --
talia-crew-brain-dump, ep1-scene-anchors, ep1-production-script and the series
bible are his authored content. His 2026-08-14 ruling applies exactly as it does
to the old @handles: SUBSTITUTE IN THE PROMPT, LEAVE THE DOCUMENT ALONE. When a
script says "stocky", write MEDIUM BUILD in the prompt and do not touch the file.
The anchor wins over anything else in this document or any other.
"""


def splice(text: str, label: str) -> str | None:
    if MARKER in text:
        return None
    for needle, what in ((OLD_ANCHOR, "anchor line"), (OLD_BUILD, "Build line")):
        if needle not in text:
            raise SystemExit(
                f"{label}: the {what} was not found byte-for-byte. "
                "Nothing was written -- resolve by hand."
            )
    text = text.replace(OLD_ANCHOR, NEW_ANCHOR, 1)
    text = text.replace(OLD_BUILD, NEW_BUILD, 1)
    return text + NOTE


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

    bak = REPO / "data" / "backup_disk_canon_before_bdubb_build_2026-08-20.md"
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
        assert NEW_ANCHOR in t, f"{label}: anchor not updated"
        assert "* Build: MEDIUM BUILD" in t, f"{label}: Build line not updated"
        assert OLD_ANCHOR not in t, f"{label}: stocky still live in the anchor"
        assert "* Build: Stocky," not in t, f"{label}: stocky still live in the Build line"
        assert 'kept on record: "Build: Stocky"' in t, f"{label}: superseded record lost"
        print(f"{label}: verified")


if __name__ == "__main__":
    main()
