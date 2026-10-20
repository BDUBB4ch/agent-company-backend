"""Seed the leadership mastery set (2026-09-09) to Victor's shelf.

Barry: "now do Victor, everything he needs." Eleven one-concern reference docs
in knowledge/leadership/ land in the NEW `domain:leadership` (granted to CIO
and Operations). On-demand; re-runnable; oversize docs skipped and named.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))

import memory  # noqa: E402

CATEGORY = "domain:leadership"
FOLDER = os.path.join(ROOT, "knowledge", "leadership")
NEW = [
    "ceo-operating-system.md",
    "strategy-and-competitive-positioning.md",
    "decision-making-and-judgment.md",
    "growth-strategy-for-a-small-ecommerce-brand.md",
    "leading-the-team.md",
    "partnerships-alliances-and-supplier-strategy.md",
    "risk-and-crisis-management-for-the-ceo.md",
    "financial-literacy-for-the-ceo.md",
    "market-and-customer-insight.md",
    "pid-venture-strategy.md",
    "how-victor-works-ceo-method.md",
]


def title_of(text: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return (m.group(1).strip() if m else fallback)[:120]


def main() -> None:
    total = 0
    skipped: list[str] = []
    present = [fn for fn in NEW if os.path.isfile(os.path.join(FOLDER, fn))]
    missing = [fn for fn in NEW if fn not in present]
    if missing:
        print("MISSING (not seeded):", ", ".join(missing))
    with memory.get_db() as conn:
        for fn in present:
            text = open(os.path.join(FOLDER, fn), encoding="utf-8").read()
            first = text.splitlines()[0] if text else ""
            assert first.startswith("USE WHEN:"), f"{fn}: first line is not USE WHEN"
            assert len(text) >= 9000, f"{fn}: only {len(text)} chars -- too thin"
            # recall injects WHOLE docs against RECALL_BUDGET 20,000 and never
            # clips -- an oversize doc is named but never read.
            if len(text) > 18500:
                # Never abort mid-shelf: an oversize doc (usually a writer still
                # trimming) is skipped and named, the rest still seed.
                print(f"  {fn:<46} {len(text):>6} chars  OVER BUDGET -- skipped, trim it")
                skipped.append(fn)
                continue
            old = conn.execute(
                "SELECT id, content FROM facts WHERE category=? AND source_name=? AND status='active'",
                (CATEGORY, fn)).fetchall()
            # Unchanged on disk and already live -> leave it alone (re-runs
            # after adding new docs must not churn the rest of the shelf).
            if old and any(r["content"].endswith(text.strip()) for r in old):
                skipped.append(fn)
                print(f"  {fn:<46} {len(text):>6} chars  (already seeded, unchanged)")
                continue
            for r in old:
                conn.execute("UPDATE facts SET status='superseded' WHERE id=?", (r["id"],))
            total += len(text)
            print(f"  {fn:<46} {len(text):>6} chars  (superseded {len(old)} old row(s))")
    for fn in present:
        if fn in skipped:
            continue
        text = open(os.path.join(FOLDER, fn), encoding="utf-8").read()
        memory.add_fact(CATEGORY, text, fn, title=title_of(text, fn[:-3]))
    print(f"seeded {len(present) - len(skipped)} docs, {total:,} chars, to {CATEGORY}")
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT source_name, length(content) n FROM facts WHERE category=? "
            "AND status='active' ORDER BY source_name", (CATEGORY,)).fetchall()
        grants = [r[0] for r in conn.execute(
            "SELECT office_name FROM agent_domains WHERE domain='leadership'")]
    print(f"shelf now: {len(rows)} active docs, {sum(r['n'] for r in rows):,} chars")
    print("granted to:", sorted(grants))
    # Routing must be visible to the index, not just present in the file.
    with memory.get_db() as conn:
        live = {r["source_name"]: dict(r) for r in conn.execute(
            "SELECT * FROM facts WHERE category=? AND status='active'", (CATEGORY,))}
    bad = [fn for fn in present if fn in live and not memory._skill_use_when(live[fn])]
    print("routing lines detected for all:", not bad, bad or "")


if __name__ == "__main__":
    main()
