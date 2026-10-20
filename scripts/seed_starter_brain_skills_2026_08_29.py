"""Seed the six Starter Brain skills (adapted from Barry's
starter-brain-plugin.zip, firstmovers.ai) into knowledge:commerce.

Business seats only -- Taliyah and Elliot are excluded from
knowledge:commerce via _SHARED_CATEGORY_EXCLUSIONS, which is correct:
these are business workflows.

Re-runnable: upserts by (source_name, category). Disk copies live in
knowledge/starter-brain/ -- edit there, re-run this.
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
import memory  # noqa: E402

CATEGORY = "knowledge:commerce"
SRC_DIR = os.path.join(ROOT, "knowledge", "starter-brain")

FILES = [
    ("daily-briefing-method.md", "daily-briefing-method"),
    ("content-engine.md", "content-engine"),
    ("lead-triage.md", "lead-triage"),
    ("voice-dna-capture.md", "voice-dna-capture"),
    ("five-tool-stack-audit.md", "five-tool-stack-audit"),
    ("context-interview-method.md", "context-interview-method"),
]


def main():
    for fname, title in FILES:
        content = open(os.path.join(SRC_DIR, fname), encoding="utf-8").read()
        assert content.startswith("USE WHEN:"), f"{fname}: missing routing line"
        with memory.get_db() as conn:
            row = conn.execute(
                "SELECT id FROM facts WHERE source_name=? AND category=? AND status='active'",
                (fname, CATEGORY)).fetchone()
            if row:
                conn.execute("UPDATE facts SET content=? WHERE id=?", (content, row[0]))
                print(f"updated {fname} (fact {row[0]}, {len(content)} chars)")
                continue
        memory.add_fact(category=CATEGORY, content=content,
                        source_name=fname, title=title)
        with memory.get_db() as conn:
            new = conn.execute(
                "SELECT id FROM facts WHERE source_name=? AND category=? AND status='active'",
                (fname, CATEGORY)).fetchone()
        print(f"created {fname} (fact {new[0]}, {len(content)} chars)")
    # verify routing lines register
    with memory.get_db() as conn:
        for fname, _ in FILES:
            row = conn.execute(
                "SELECT content FROM facts WHERE source_name=? AND category=? AND status='active'",
                (fname, CATEGORY)).fetchone()
            # add_fact prepends a TITLE line (house rule), so USE WHEN sits
            # on line 2 -- _skill_use_when scans the first 1200 chars.
            assert row and "USE WHEN:" in row[0][:1200], f"{fname}: verify failed"
    print("all six verified in the brain")


if __name__ == "__main__":
    main()
