"""Change "Stocky" -> "Medium-build" in Barry's MAIN SCRIPT (fact 466,
ep1-wrong-box-script-CANON-v7.md), on his instruction 2026-08-20:

    "change it in my main script too so he can just refer to it when i tell him"

This is Barry reversing his own 2026-08-14 "substitute in the prompt, never edit the
script" rule for this one word, in this one file. He asked; that is the authority.

DELIBERATELY MINIMAL. One word, one file. No note is inserted into his script, no
formatting is touched, nothing else is rewritten -- "dont change anything else" is
still the standing rule around this. The record of the change lives in the backup
file and in the canon ruling, NOT inside his authored document.

NOT touched (his authored content, he scoped this to the main script):
  fact 467 ep1-scene-anchors.md          2 hits
  fact 468 ep1-scene-anchor-prompts.md   3 hits   <-- PINNED for Elliot
  fact 473 ep1-production-script.md      1 hit
  facts 171 / 174 / 212 / 458 (lore, premise, overview, series bible)

Written as a script file, never through bash -c python -c.
"""
import pathlib
import sqlite3

REPO = pathlib.Path(__file__).resolve().parent.parent
DB = REPO / "data" / "brain.db"
FACT_ID = 466
OLD = "Stocky Black American Indian male"
NEW = "Medium-build Black American Indian male"


def main() -> None:
    conn = sqlite3.connect(DB)
    row = conn.execute(
        "SELECT source_name, content FROM facts WHERE id = ?", (FACT_ID,)
    ).fetchone()
    if row is None:
        raise SystemExit(f"fact {FACT_ID} not found -- nothing written.")
    source_name, content = row

    if "ep1-wrong-box-script-CANON-v7" not in source_name:
        raise SystemExit(
            f"fact {FACT_ID} is '{source_name}', not the CANON v7 script. "
            "Nothing written -- the fact id has moved, check before editing."
        )

    n = content.count(OLD)
    if n == 0:
        if NEW in content:
            print("already applied -- nothing to do")
            return
        raise SystemExit(
            "the exact phrase was not found in the script. Nothing written -- "
            "resolve by hand rather than guessing at a looser match."
        )
    if n != 1:
        raise SystemExit(
            f"expected exactly 1 occurrence, found {n}. Nothing written -- "
            "a multi-hit replace on his authored script needs his say-so first."
        )

    bak = REPO / "data" / f"backup_fact{FACT_ID}_ep1_canon_v7_before_bdubb_build_2026-08-20.md"
    if not bak.exists():
        bak.write_text(content, encoding="utf-8")
    print(f"backup: {bak.name}  ({len(content):,} chars)")

    updated = content.replace(OLD, NEW, 1)
    conn.execute("UPDATE facts SET content = ? WHERE id = ?", (updated, FACT_ID))
    conn.commit()

    after = conn.execute("SELECT content FROM facts WHERE id = ?", (FACT_ID,)).fetchone()[0]
    assert NEW in after, "replacement missing after write"
    assert OLD not in after, "old wording still present"
    # length must differ by exactly the word-length delta -- proves nothing else moved
    delta = len(after) - len(content)
    assert delta == len(NEW) - len(OLD), f"unexpected length change: {delta}"
    print(f"fact {FACT_ID} ({source_name}) -> {len(content):,} -> {len(after):,} chars "
          f"(delta {delta:+d}, one word only)")
    print("verified")


if __name__ == "__main__":
    main()
