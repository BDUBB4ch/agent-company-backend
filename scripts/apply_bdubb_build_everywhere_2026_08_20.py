"""Change "stocky" -> "medium build" in EVERY remaining active fact, on Barry's
instruction 2026-08-20: "change it everywhere".

Follows apply_bdubb_build_to_script_2026_08_20.py, which did the main script (fact 466)
alone. This finishes the job across his scene anchors, production script and lore docs.

MECHANICAL AND MINIMAL. Only the word "stocky" changes. Two forms, chosen by what
follows the word so the prose still reads correctly:

    "Build: Stocky."            -> "Build: Medium build."      (standalone sentence)
    "stocky Black American..."  -> "medium-build Black American..."   (adjective)

Capitalisation is preserved. Nothing else in any document is touched -- no notes
inserted, no formatting changed. His documents stay his; the record of the change is
the per-fact backup file plus the ruling in the canon.

Every fact is backed up to data/backup_bdubb_build_2026-08-20/ before it is written,
and the whole run aborts if any fact would change by an unexpected number of bytes.

DELIBERATELY NOT TOUCHED:
  * knowledge/character-visual-canon.md -- Claude-written, ALL its facts are already
    status='superseded' and it is the file Barry rejected ("no only original stuff
    should go to my agents"). It says "Stocky, broad-built man"; editing one word of a
    dead document is noise. Flagged, not changed.
  * scripts/apply_anchor_bible_2026_08_08.py -- a historical record of what was applied
    that day. Rewriting history would be a lie about what happened.

Written as a script file, never through bash -c python -c.
"""
import pathlib
import re
import sqlite3

REPO = pathlib.Path(__file__).resolve().parent.parent
DB = REPO / "data" / "brain.db"
BAKDIR = REPO / "data" / "backup_bdubb_build_2026-08-20"

# word "stocky" followed by a period/sentence end -> standalone noun phrase.
STANDALONE = re.compile(r"\bstocky\b(?=\s*[.;,]?\s*(?:\*\*)?[A-Z])", re.IGNORECASE)
WORD = re.compile(r"\bstocky\b", re.IGNORECASE)


def _cased(replacement: str, original: str) -> str:
    """Match the capitalisation of the word being replaced."""
    if original[0].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def convert(text: str) -> str:
    def sub(m: re.Match) -> str:
        word = m.group(0)
        after = text[m.end():m.end() + 2]
        # "Stocky." / "Stocky," ending a clause -> noun phrase, else adjective
        if after[:1] in (".", ";"):
            return _cased("medium build", word)
        return _cased("medium-build", word)

    return WORD.sub(sub, text)


def main() -> None:
    conn = sqlite3.connect(DB)
    rows = conn.execute(
        "SELECT id, source_name, content FROM facts "
        "WHERE status = 'active' AND lower(content) LIKE '%stocky%' ORDER BY id"
    ).fetchall()

    if not rows:
        print("no active facts contain 'stocky' -- nothing to do")
        return

    BAKDIR.mkdir(exist_ok=True)
    planned = []
    for fid, source_name, content in rows:
        updated = convert(content)
        hits = len(WORD.findall(content))
        delta = len(updated) - len(content)
        # every hit grows by 6 ("medium build"/"medium-build" are both 12 chars vs 6)
        if delta != hits * 6:
            raise SystemExit(
                f"fact {fid} ({source_name}): expected +{hits * 6} bytes, got {delta:+d}. "
                "Nothing written -- a replace touched more than the word."
            )
        if WORD.search(updated):
            raise SystemExit(f"fact {fid}: 'stocky' survived the replace. Nothing written.")
        planned.append((fid, source_name, content, updated, hits, delta))

    print(f"{len(planned)} fact(s) to update:\n")
    for fid, source_name, content, updated, hits, delta in planned:
        bak = BAKDIR / f"fact{fid}_{re.sub(r'[^A-Za-z0-9._-]', '_', source_name)}.md"
        if not bak.exists():
            bak.write_text(content, encoding="utf-8")
        conn.execute("UPDATE facts SET content = ? WHERE id = ?", (updated, fid))
        print(f"  fact {fid:<4} {source_name[:44]:<46} {hits} hit(s)  "
              f"{len(content):,} -> {len(updated):,} ({delta:+d})")
    conn.commit()
    print(f"\nbackups -> {BAKDIR.relative_to(REPO)}/")

    remaining = conn.execute(
        "SELECT id, source_name FROM facts "
        "WHERE status = 'active' AND lower(content) LIKE '%stocky%'"
    ).fetchall()
    assert not remaining, f"still contain stocky after write: {remaining}"
    print("verified: zero active facts contain 'stocky'")

    # spot-check the two that matter most
    for fid in (466, 468):
        c = conn.execute("SELECT content FROM facts WHERE id = ?", (fid,)).fetchone()
        if c and "medium-build" in c[0].lower():
            print(f"  fact {fid}: medium-build present")


if __name__ == "__main__":
    main()
