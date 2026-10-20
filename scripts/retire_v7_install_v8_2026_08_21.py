"""Retire ALL old EP1 script versions from Elliot; install the updated V8.

Barry, 2026-08-21: "delete V7 from elliot and any other Version and add this new
V8 with updated character canon ancors."

RETIRED (status='superseded' -- NEVER hard-deleted; restore = flip status back):
  466 ep1-wrong-box-script-CANON-v7.md   (94,385)  the V7 production script
  467 ep1-scene-anchors.md               (26,428)  EP1 anchor doc
  468 ep1-scene-anchor-prompts.md        (22,120)  EP1 anchor prompts (was PINNED
                                                    -- pin removed in agents.py
                                                    in the same change)
  473 ep1-production-script.md           (49,546)  older production script
  (the pre-v7 versions -- 55/58/463-465/469-472 -- were already superseded)
KEPT: the Talia Crew LORE docs (brain-dump, premise, overview, series bible) --
those are world/story reference, not script versions. Canon untouched.

INSTALLED: ep1-treatment-v8.md reactivated with the ANCHOR-UPDATED treatment
(data/ep1_treatment_v8_verbatim.md as of 2026-08-21 -- anchors now match current
canon: medium-build/slightly-muscular B Dubb, Yannah's new baseline w/ machine
pistol and no forearm unit, Tazz all-black + missile blaster, Keth dark green
eyes). Header rewritten: the old "ignore the anchors, they're stale" warning is
GONE because it is no longer true.

Every retired fact's content is backed up to data/backup_retired_scripts_2026-08-21/.
"""
import pathlib
import sqlite3
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import memory

BAK = REPO / "data" / "backup_retired_scripts_2026-08-21"
RETIRE_IDS = [466, 467, 468, 473]

HEADER = """EP1 "WRONG BOX" -- V8 DIRECTOR'S TREATMENT (Barry; anchors updated 2026-08-21)
USE WHEN: any ask about the V8 treatment as a whole; the act/scene chunks (ep1-v8-*) carry the working text for conversion passes.

THIS IS THE EPISODE'S SOURCE DOCUMENT. Barry retired V7 and every older version
on 2026-08-21 ("delete V7 from elliot and any other Version and add this new
V8"). The CHARACTER ANCHORS below were updated the same day to his CURRENT
canon -- they are live, not stale. If this document and barry-character-canon
ever disagree, THE CANON WINS. The V8 production script is being built pass by
pass into ep1-production-v8-WIP.

--- THE V8 TREATMENT, VERBATIM, BEGINS BELOW ---

"""


def main() -> None:
    conn = sqlite3.connect(REPO / "data" / "brain.db")
    BAK.mkdir(exist_ok=True)

    for fid in RETIRE_IDS:
        row = conn.execute(
            "SELECT source_name, status, content FROM facts WHERE id = ?", (fid,)
        ).fetchone()
        if row is None:
            print(f"  fact {fid}: MISSING -- skipped")
            continue
        src, status, content = row
        p = BAK / f"fact{fid}_{src.replace('/', '_')}"
        if not p.exists():
            p.write_text(content, encoding="utf-8")
        if status == "active":
            conn.execute("UPDATE facts SET status='superseded' WHERE id = ?", (fid,))
            print(f"  fact {fid} {src:42} -> superseded (backed up)")
        else:
            print(f"  fact {fid} {src:42} already {status}")
    conn.commit()

    body = (REPO / "data" / "ep1_treatment_v8_verbatim.md").read_text(encoding="utf-8")
    assert "Medium-build, slightly muscular" in body, "anchor update missing from source file"
    content = HEADER + body
    row = conn.execute(
        "SELECT id FROM facts WHERE source_name='ep1-treatment-v8.md' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row:
        conn.execute("UPDATE facts SET content=?, status='active' WHERE id=?",
                     (content, row[0]))
        conn.commit()
        print(f"  ep1-treatment-v8.md reactivated (fact {row[0]}, {len(content):,} chars)")
    else:
        memory.add_fact(category="private:MovieDirector", content=content,
                        source_name="ep1-treatment-v8.md",
                        title="EP1 WRONG BOX -- V8 treatment (anchors updated 2026-08-21)")
        print(f"  ep1-treatment-v8.md created ({len(content):,} chars)")

    # verify Elliot's view of the world
    active = {f.get("source_name") for f in memory.get_active_facts_for_agent("MovieDirector")}
    for gone in ("ep1-wrong-box-script-CANON-v7.md", "ep1-scene-anchors.md",
                 "ep1-scene-anchor-prompts.md", "ep1-production-script.md"):
        assert gone not in active, f"{gone} still active!"
    assert "ep1-treatment-v8.md" in active
    assert "ep1-v8-act1-colorado.md" in active
    print("verified: V7 and all old versions gone from Elliot; V8 treatment + chunks active")
    print(f"RESTORE any doc: UPDATE facts SET status='active' WHERE id IN {tuple(RETIRE_IDS)}")


if __name__ == "__main__":
    main()
