"""Pin the approval-status nuance into bionova-suggested-retail-2025.

2026-08-16: measured twice in phase-5 probes, Amara states Barry's Oct-2025
retail plan was "approved by Bionova with zero restrictions", quoting his
real "price it how we want" line as evidence. That line (fact 649, the
Winter/channel note) is about PRICING FREEDOM under the distribution deal;
whether Bionova ever approved the specific submitted Oct-2025 plan is
recorded in the doc itself as an OPEN QUESTION. The model fuses the two.
Prompt rules didn't stop it because the model believes it knows -- so the
correction goes into the data it reasons from.

Re-runnable: skips if the status line is already present.
"""

import os
import sqlite3

STATUS = (
    "\nSTATUS -- READ BEFORE CITING APPROVAL: whether Bionova approved this "
    "specific Oct-2025 plan is an OPEN QUESTION -- do not state that they "
    "approved it. Do not confuse it with Barry's separate, real pricing "
    "freedom under the Winter distribution deal (\"Bionova left it up to me "
    "and winter... price it how we want\") -- that is freedom to set store "
    "prices, not an approval of this submitted plan. If it matters to an "
    "answer, say the approval status is unconfirmed and ask Barry.\n"
)


def main():
    db = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "brain.db")
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT id, content FROM facts WHERE status='active' AND source_name LIKE "
        "'bionova-suggested-retail-2025%'").fetchone()
    if not row:
        print("Doc not found -- nothing changed.")
        return
    fid, content = row
    if "READ BEFORE CITING APPROVAL" in content:
        print(f"Fact {fid} already carries the status line.")
        return
    lines = content.split("\n")
    at = 1 if lines else 0  # right under the title line
    updated = "\n".join(lines[:at] + [STATUS] + lines[at:])
    conn.execute("UPDATE facts SET content=? WHERE id=?", (updated, fid))
    conn.commit()
    conn.close()
    print(f"Fact {fid} updated -- status line added under the title.")


if __name__ == "__main__":
    main()
