"""Repair fact 592 after apply_bdubb_build_everywhere_2026_08_20.py wrongly included it.

WHAT WENT WRONG. The "change it everywhere" sweep replaced the word in every active
fact -- including the canon itself. The canon is the one document that MUST keep the
old word, because it carries the SUPERSEDED RECORD and the synonym warning. The sweep
turned Barry's quote into "medium build not medium build", rewrote the on-record
"Build: Stocky" line, and made the warning read "Not medium-build, not heavy-set".
It also left fact 592 (83,802) drifted from the disk copy (83,754).

THE FIX, in two steps:
  1. Restore fact 592 from the backup that sweep made -- that file is the correct
     post-ruling state and is byte-identical to the disk copy.
  2. Update the one paragraph that is now genuinely out of date in BOTH copies: it
     said his story documents still say the old word and must not be edited. He then
     told us to change them, and we did. It has to say that instead.

Written as a script file, never through bash -c python -c.
"""
import pathlib
import sqlite3

REPO = pathlib.Path(__file__).resolve().parent.parent
DISK = REPO / "data" / "barry-character-canon.md"
DB = REPO / "data" / "brain.db"
# note the doubled .md -- the sweep appended .md to a source_name that already had one
BAK = REPO / "data" / "backup_bdubb_build_2026-08-20" / "fact592_barry-character-canon.md.md"

OLD_PARA = """⚠️ HIS OWN STORY DOCUMENTS STILL SAY "STOCKY" and are NOT to be edited --
talia-crew-brain-dump, ep1-scene-anchors, ep1-production-script and the series
bible are his authored content. His 2026-08-14 ruling applies exactly as it does
to the old @handles: SUBSTITUTE IN THE PROMPT, LEAVE THE DOCUMENT ALONE. When a
script says "stocky", write MEDIUM BUILD in the prompt and do not touch the file.
The anchor wins over anything else in this document or any other."""

NEW_PARA = """HIS DOCUMENTS WERE CHANGED TOO -- Barry, 2026-08-20: "change it everywhere."

He reversed his own 2026-08-14 substitute-never-edit rule for this one word, and
the word was replaced in his main script and in every other active document that
carried it: ep1-scene-anchors, ep1-scene-anchor-prompts, ep1-production-script,
talia-crew-brain-dump, talia-crew-premise, talia-crew-project-overview and the
Talia Crew series bible. One word each, nothing else touched, every fact backed
up to data/backup_bdubb_build_2026-08-20/.

  * THIS WAS A PER-REQUEST EXCEPTION, NOT A NEW LICENCE. The 2026-08-14 ruling
    still governs every other difference between an old document and current
    canon -- old @handles, the old weapon wordings, anything else that has moved:
    SUBSTITUTE IN THE PROMPT, LEAVE THE DOCUMENT ALONE, unless he names the
    change himself as he did here.
  * THE ANCHOR STILL WINS over anything else in this document or any other."""

MARKER = 'HIS DOCUMENTS WERE CHANGED TOO -- Barry, 2026-08-20: "change it everywhere."'


def main() -> None:
    conn = sqlite3.connect(DB)
    current = conn.execute("SELECT content FROM facts WHERE id = 592").fetchone()[0]

    # --- step 1: restore fact 592 if the sweep corrupted it -------------------
    if "medium build not medium build" in current:
        if not BAK.exists():
            raise SystemExit(f"backup missing: {BAK} -- cannot restore, nothing written.")
        restored = BAK.read_text(encoding="utf-8")
        assert "medium build not stocky" in restored, "backup is not the expected state"
        conn.execute("UPDATE facts SET content = ? WHERE id = 592", (restored,))
        conn.commit()
        print(f"fact 592 restored from backup -> {len(restored):,} chars")
        current = restored
    else:
        print("fact 592: not corrupted, no restore needed")

    disk_text = DISK.read_text(encoding="utf-8")
    if disk_text != current:
        raise SystemExit(
            f"disk ({len(disk_text):,}) and fact 592 ({len(current):,}) still differ "
            "after restore. Nothing further written -- resolve by hand."
        )
    print("disk and fact 592 are byte-identical again")

    # --- step 2: correct the now-outdated paragraph in both copies ------------
    if MARKER in current:
        print("paragraph already corrected -- nothing to do")
        return
    if OLD_PARA not in current:
        raise SystemExit("the outdated paragraph was not found byte-for-byte. Nothing written.")

    updated = current.replace(OLD_PARA, NEW_PARA, 1)
    DISK.write_text(updated, encoding="utf-8")
    conn.execute("UPDATE facts SET content = ? WHERE id = 592", (updated,))
    conn.commit()
    print(f"both copies -> {len(current):,} -> {len(updated):,} chars")

    after_disk = DISK.read_text(encoding="utf-8")
    after_fact = conn.execute("SELECT content FROM facts WHERE id = 592").fetchone()[0]
    assert after_disk == after_fact, "copies drifted during the write"
    for check in (
        MARKER,
        'my character B dubb is supposed to be medium build not stocky',
        'kept on record: "Build: Stocky"',
        'His 2026-08-08 anchor said "Stocky Black American Indian male"',
        'HE IS MEDIUM BUILD. Not stocky',
        '@B DUBB: MEDIUM-BUILD Black American Indian male',
    ):
        assert check in after_fact, f"missing after write: {check[:60]}"
    print("verified: ruling intact, superseded record intact, copies in sync")


if __name__ == "__main__":
    main()
