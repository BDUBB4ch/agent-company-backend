"""Third pass on the conversation-history routing lines (supersedes the
earlier version of this script, which spelled the month out but kept
shared boilerplate).

WHY: v1/v2 lines all shared "discussed, decided, worked on, refers back,
conversation" -- so much common vocabulary across 16 docs that a generic
ask ("refresh me on the may 5 conversation") scored a random PACK of
histories. Routing lines are contracts; sixteen near-identical ones are
one indistinct blob. These are slimmed to date-specific tokens only --
recall's date door (recall.py section 1a2) handles dated asks directly,
and an undated "that conversation" ask has no right answer anyway.

Rewrites ONLY the USE WHEN first line; content below untouched. Idempotent.

Usage:  ../venv/Scripts/python.exe scripts/fix_history_routing_dates_2026_08_25.py
"""
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import memory  # noqa: E402


def main() -> None:
    facts = memory.get_active_facts_for_agent("MovieDirector")
    fixed = 0
    with memory.get_db() as conn:
        for f in facts:
            sn = f.get("source_name") or ""
            if not sn.startswith("conversation-history"):
                continue
            m = re.search(r"(\d{4})-(\d{2})-(\d{2})", sn)
            if not m:
                continue
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            spoken = f"{d.strftime('%B').lower()} {d.day}"
            iso = m.group(0)
            line = f"USE WHEN: Barry asks about the {iso} ({spoken}) conversation."
            first, _, rest = f["content"].partition("\n")
            if not first.lower().startswith("use when:"):
                continue  # never touch a doc this pass didn't tag
            if first == line:
                continue  # already slimmed
            conn.execute("UPDATE facts SET content = ? WHERE id = ?",
                         (line + "\n" + rest, f["id"]))
            fixed += 1
    print(f"slimmed {fixed} history routing lines")


if __name__ == "__main__":
    main()
