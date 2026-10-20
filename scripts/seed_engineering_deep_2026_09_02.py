"""Seed Sophie's coding curriculum (2026-09-02) to the engineering shelf.

Barry: "i need her to be a really good coder. if i have to find stuff for her
then i will unless you can find high level coding lessons for her to learn and
writing."

Ten one-concern lessons in knowledge/engineering/, each written FOR Sophie
(a local 27B agent who edits code by exact-snippet replacement and explains
every change to a non-coder), each with a USE WHEN routing line and a
"traps this office has actually hit" section drawn from the build record.
They land in `domain:engineering` -- the domain only the Engineer seat holds
-- as on-demand `.md` facts, so zero always-on cost; recall serves them when
the matching kind of work comes up. Re-runnable: same source_name supersedes
the old row, never deletes it.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))

import memory  # noqa: E402

CATEGORY = "domain:engineering"
FOLDER = os.path.join(ROOT, "knowledge", "engineering")
NEW = [
    "python-mastery.md",
    "async-and-concurrency.md",
    "fastapi-and-http.md",
    "sqlite-and-data.md",
    "javascript-for-the-decks.md",
    "reading-and-changing-code-safely.md",
    "testing-and-verification.md",
    "regex-and-text-processing.md",
    "technical-writing-eli17.md",
    "performance-and-profiling.md",
]


def title_of(text: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return (m.group(1).strip() if m else fallback)[:120]


def main() -> None:
    total = 0
    with memory.get_db() as conn:
        for fn in NEW:
            path = os.path.join(FOLDER, fn)
            text = open(path, encoding="utf-8").read()
            first = text.splitlines()[0] if text else ""
            assert first.startswith("USE WHEN:"), f"{fn}: first line is not USE WHEN"
            assert len(first) <= 260, f"{fn}: USE WHEN line too long ({len(first)})"
            assert len(text) >= 7000, f"{fn}: only {len(text)} chars -- too thin"
            # recall injects WHOLE docs and never clips: anything over
            # RECALL_BUDGET (20,000) is NAMED but never loaded -- the V8 lesson.
            assert len(text) <= 18500, f"{fn}: {len(text)} chars -- over the recall budget, split or trim it"
            old = conn.execute(
                "SELECT id FROM facts WHERE category=? AND source_name=? AND status='active'",
                (CATEGORY, fn)).fetchall()
            for r in old:
                conn.execute("UPDATE facts SET status='superseded' WHERE id=?", (r["id"],))
            total += len(text)
            print(f"  {fn:<40} {len(text):>6} chars  (superseded {len(old)} old row(s))")
    for fn in NEW:
        text = open(os.path.join(FOLDER, fn), encoding="utf-8").read()
        memory.add_fact(CATEGORY, text, fn, title=title_of(text, fn[:-3]))
    print(f"seeded {len(NEW)} docs, {total:,} chars, to {CATEGORY}")
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT source_name, length(content) n FROM facts WHERE category=? "
            "AND status='active' ORDER BY source_name", (CATEGORY,)).fetchall()
        grants = [r[0] for r in conn.execute(
            "SELECT office_name FROM agent_domains WHERE domain='engineering'")]
    print(f"shelf now: {len(rows)} active docs, {sum(r['n'] for r in rows):,} chars")
    print("granted to:", sorted(grants))
    # routing lines actually parse
    for fn in NEW:
        uw = memory._skill_use_when({"content": open(os.path.join(FOLDER, fn), encoding="utf-8").read()})
        assert uw, f"{fn}: _skill_use_when found no routing line"
    print("all routing lines parse")


if __name__ == "__main__":
    main()
