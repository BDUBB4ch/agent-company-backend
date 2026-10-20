"""Stamp the Bionova evidence docs: the STORE price is the price.

Barry, 2026-09-17: "i think we lowered the prices on some. she should refer
to the store prices which is what people see." Measured that day: the docs
say MgO 10 $24.95 / Ca 15 $21.95; the live store says $23.95 / $22.95 -- drift
in BOTH directions since the August seeding. Amara already did the right
thing (lookup_product, quoted $23.95); this makes the RECORD say so, once,
dated, instead of re-editing every price that will drift again.

Prepends one banner under the USE WHEN line of facts 646/647/648 AND their
disk twins in knowledge/bdubb-products/, asserts both copies byte-identical
after (the two-copies drift rule). Idempotent: a doc already stamped is left
alone. Never touches the numbers themselves -- they are the dated evidence.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))

import memory  # noqa: E402

CATEGORY = "business:bdubbgrows"
DOCS = ["bionova-cost-basis.md", "bionova-wholesale-pricelist.md",
        "bionova-suggested-retail-2025.md"]
MARK = "STORE PRICE WINS (Barry, 2026-09-17)"
BANNER = (
    f"\n⚠️ {MARK}: every RETAIL price written in this document is a snapshot "
    "from the day it was written and has already drifted (measured 2026-09-17: "
    "MgO 10 1L is $23.95 live, not $24.95; Ca 15 1L is $22.95 live, not $21.95). "
    "The price customers see on bdubbgrowsllc.com is the price. Before quoting, "
    "comparing or computing a margin on any product, read it live with "
    "lookup_product / read_product and use THAT number; the figures here are "
    "for the cost side and for the history of the decisions, never for the "
    "current shelf price. Barry: \"she should refer to the store prices which "
    "is what people see.\"\n"
)


def stamp(text: str) -> str:
    if MARK in text:
        return text
    lines = text.split("\n")
    for i, l in enumerate(lines):
        if l.strip().upper().startswith("USE WHEN:"):
            return "\n".join(lines[: i + 1] + [BANNER] + lines[i + 1:])
    # no USE WHEN line: after the first heading
    for i, l in enumerate(lines):
        if l.startswith("#"):
            return "\n".join(lines[: i + 1] + [BANNER] + lines[i + 1:])
    return BANNER + "\n" + text


def main() -> None:
    for fn in DOCS:
        disk_path = os.path.join(ROOT, "knowledge", "bdubb-products", fn)
        with memory.get_db() as conn:
            row = conn.execute(
                "SELECT id, content FROM facts WHERE category=? AND source_name=? AND status='active'",
                (CATEGORY, fn)).fetchone()
        assert row, f"{fn}: no active fact in {CATEGORY}"
        fact_text = row["content"]
        # add_fact prepended a TITLE line above the disk text; strip it so both
        # copies are compared on the same body.
        disk_text = open(disk_path, encoding="utf-8").read() if os.path.isfile(disk_path) else None
        new_fact = stamp(fact_text)
        if new_fact == fact_text:
            print(f"  {fn:<40} already stamped")
        else:
            with memory.get_db() as conn:
                conn.execute("UPDATE facts SET content=? WHERE id=?", (new_fact, row["id"]))
            print(f"  {fn:<40} fact {row['id']} stamped (+{len(new_fact) - len(fact_text)} chars)")
        if disk_text is not None:
            new_disk = stamp(disk_text)
            if new_disk != disk_text:
                with open(disk_path, "w", encoding="utf-8", newline="") as fh:
                    fh.write(new_disk)
                print(f"  {'':<40} disk copy stamped")
            # both copies must carry the same body (fact has a TITLE line on
            # top, and add_fact may leave extra blank lines under it --
            # measured on 648: the ONLY difference was two blank lines).
            # Compare on non-blank lines so real drift fails and whitespace
            # does not.
            body = lambda t: [l.rstrip() for l in t.split("\n") if l.strip()]
            fb, db = body(new_fact), body(new_disk)
            assert fb[-len(db):] == db, \
                f"{fn}: fact and disk copy differ beyond the title line -- diff before syncing"
        with memory.get_db() as conn:
            live = conn.execute("SELECT content FROM facts WHERE id=?", (row["id"],)).fetchone()["content"]
        assert MARK in live and memory._skill_use_when({"content": live}), f"{fn}: routing line lost"
    print("done: banner present in all three facts, routing intact, disk twins in sync")


if __name__ == "__main__":
    main()
