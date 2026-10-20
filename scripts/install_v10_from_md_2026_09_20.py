"""Re-install V10 from Barry's .md, replacing the lossy .docx extraction.

WHY: the .docx path lost ~3,900 characters -- most importantly the VOICE LOCKS
table, so @Keth's voice id (6b528d43-...) was missing entirely from the
installed script. python-docx flattens tables; the .md keeps them. Verified
before install: .md has all six roster ids, .docx had five.

Adds only the `_SEP` rule lines script_wip needs to find block boundaries
(a .md has none) -- proved content-neutral by stripping them back out and
comparing byte for byte.
"""
import glob
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import memory  # noqa: E402
import script_wip  # noqa: E402

MD = r"C:\Users\Owner\Downloads\TALIA_CREW_EP1_V10_RENUMBERED.md"
CATEGORY = f"private:{script_wip.OFFICE}"

ROSTER = {
    "@b-dubb": "9b162037-e549-4065-9562-ebac293ee72a",
    "@Bia-2": "f32c8f51-449e-4ddf-bdf7-1527e11df917",
    "@Yannah": "032386ec-491b-5bdc-81ac-49e9a6a2c89d",
    "@Tazz": "3811e986-0891-47cf-a1f5-78a1d62a547a",
    "@Keth": "6b528d43-c056-4a2f-9d82-1591a7ba13b0",
    "@lady-vor-shara-vel": "d081b915-6623-4a44-bacf-80d0f1c90a03",
}
# strip markdown decoration the way _block_label does, then match a label
HEAD = re.compile(r"^((?:SHOT|B-ROLL|SCENE|TITLE CARD)\s+[0-9A-Za-z]+)\b", re.I)


def main() -> int:
    text = open(MD, encoding="utf-8").read()

    assert text.count("\ufffd") == 0, "source has lost characters"
    missing = [h for h, v in ROSTER.items() if v not in text]
    assert not missing, f"voice ids missing from the .md: {missing}"
    print(f"source OK: {len(text):,} chars, all 6 voice ids present")

    # --- insert separators above each block header ---------------------------
    out, inserted = [], 0
    for line in text.split("\n"):
        bare = line.strip().lstrip("#*[ ").rstrip("]#* ")
        if HEAD.match(bare) and out:
            out.append(script_wip._SEP)
            inserted += 1
        out.append(line)
    new = "\n".join(out)
    restored = "\n".join(l for l in new.split("\n") if l != script_wip._SEP)
    assert restored == text, "separator insertion altered his text -- aborting"
    print(f"inserted {inserted} separators, content byte-identical after strip")

    # --- replace the installed fact in place --------------------------------
    cands = glob.glob(os.path.join(ROOT, "data", "*.db"))
    db = [c for c in cands if "brain" in os.path.basename(c)] or cands
    con = sqlite3.connect(db[0])
    cur = con.cursor()
    cur.execute("select id from facts where source_name=? and status='active'",
                (script_wip.WIP_SOURCE,))
    row = cur.fetchone()
    if row:
        with memory.get_db() as conn:
            conn.execute("UPDATE facts SET content = ? WHERE id = ?", (new, row[0]))
        print(f"replaced fact {row[0]} (was the .docx extraction)")
    else:
        memory.add_fact(category=CATEGORY, content=new,
                        source_name=script_wip.WIP_SOURCE,
                        title="EP1 WRONG BOX -- production script V10 (renumbered, canon)")
        print("installed fresh")

    # --- ledger + proof ------------------------------------------------------
    cur.execute("select id, content from facts where source_name=? and status='active'",
                (script_wip.WIP_SOURCE,))
    fid, stored = cur.fetchone()
    assert text in "\n".join(l for l in stored.split("\n") if l != script_wip._SEP)
    header, blocks = script_wip._split_blocks(stored)
    script_wip._regenerate_ledger(blocks)
    labels = [script_wip._block_label(b) for b in blocks]
    print(f"fact {fid}: {len(stored):,} chars, {len(blocks)} blocks")
    print("labels:", " | ".join(l or "(unlabelled)" for l in labels))
    print("unlabelled:", [i for i, l in enumerate(labels) if not l] or "NONE")
    for h, v in ROSTER.items():
        print(f"  {h:<22} voice id present: {v in stored}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
