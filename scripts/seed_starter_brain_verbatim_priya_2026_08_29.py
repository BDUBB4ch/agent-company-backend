"""Put the Starter Brain ZIP itself into Priya's brain, VERBATIM.

Barry, 2026-08-29: "did you actually give Priya the zip or just taught her
some of what was there? I want that zip in her brain."

He was right to ask. The earlier seeder
(seed_starter_brain_skills_2026_08_29.py) wrote CLAUDE'S ADAPTATIONS of the
six skills into knowledge:commerce. Useful, but they are my wording, not the
source. This script seeds the original documents byte-for-byte into
private:Operations so Priya holds the actual material.

Each fact = a short routing header (so recall can find it) + the untouched
file body under a VERBATIM marker. Nothing is summarized -- same rule as
Barry's own canon: store the real words, never a paraphrase.

Re-runnable: ingest.teach upserts by title.
Source: Barry's starter-brain-plugin.zip (firstmovers.ai), extracted copy
kept at data/starter-brain-source/ so this is reproducible without the zip.
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
import ingest   # noqa: E402
import memory   # noqa: E402

SRC = os.path.join(ROOT, "data", "starter-brain-source")
OFFICE = "Operations"

# (relative path, fact title, USE WHEN routing line)
DOCS = [
    ("README.md", "starter-brain-readme",
     "asked what the Starter Brain is, what the six workflows are, or where "
     "the whole system came from."),
    ("INSTALL.md", "starter-brain-install",
     "asked how the Starter Brain plugin is installed or set up on Claude "
     "Code (plumbing -- rarely needed in the office)."),
    ("commands/setup.md", "starter-brain-setup-command",
     "walking Barry through first-time Starter Brain setup end to end."),
    ("assets/business-brain-template.md", "starter-brain-business-brain-template",
     "building or updating Barry's master business context file -- the full "
     "section-by-section template."),
    ("assets/voice-dna-interview.md", "starter-brain-voice-dna-questions",
     "running Barry's voice interview -- the exact 15 questions, beliefs, "
     "stories and sound."),
    ("skills/business-brain/SKILL.md", "starter-brain-skill-business-brain",
     "creating, loading or updating the Business Brain context file."),
    ("skills/voice-dna/SKILL.md", "starter-brain-skill-voice-dna",
     "capturing how Barry sounds, or content comes back sounding generic."),
    ("skills/content-engine/SKILL.md", "starter-brain-skill-content-engine",
     "turning one idea into a week of content, repurposing, or writing "
     "posts, newsletters, scripts and threads."),
    ("skills/daily-briefing/SKILL.md", "starter-brain-skill-daily-briefing",
     "giving Barry a morning briefing or deciding what he should focus on."),
    ("skills/lead-triage/SKILL.md", "starter-brain-skill-lead-triage",
     "scoring inbound inquiries and drafting replies to leads."),
    ("skills/tool-stack-audit/SKILL.md", "starter-brain-skill-tool-stack-audit",
     "auditing tools and subscriptions, or deciding what to cancel."),
]


def main():
    seeded = []
    for rel, title, use_when in DOCS:
        path = os.path.join(SRC, rel)
        body = open(path, encoding="utf-8").read()
        assert body.strip(), f"{rel}: empty"
        text = (
            f"USE WHEN: {use_when}\n\n"
            f"SOURCE DOCUMENT -- VERBATIM, from Barry's Starter Brain plugin "
            f"(firstmovers.ai), file `{rel}`. These are the original author's "
            f"words, reproduced exactly. Claude's office-adapted versions of "
            f"these workflows live separately in knowledge:commerce; where "
            f"the two differ, THIS is the source.\n\n"
            f"----- BEGIN {rel} -----\n"
            f"{body}\n"
            f"----- END {rel} -----\n"
        )
        ingest.teach(OFFICE, "knowledge", text, title=title)
        seeded.append((title, len(body)))
        print(f"seeded {title:45s} <- {rel} ({len(body)} chars verbatim)")

    # verify: every doc present, on-demand, routed, and body intact
    with memory.get_db() as conn:
        for (rel, title, _), (_, blen) in zip(DOCS, seeded):
            row = conn.execute(
                "SELECT source_name, content FROM facts WHERE category=? "
                "AND status='active' AND content LIKE ?",
                (f"private:{OFFICE}", f"%----- BEGIN {rel} -----%")).fetchone()
            assert row, f"{title}: not found after write"
            assert row["source_name"].endswith(".md"), \
                f"{title}: not on-demand ({row['source_name']})"
            assert "USE WHEN:" in row["content"][:1200], f"{title}: not routed"
            original = open(os.path.join(SRC, rel), encoding="utf-8").read()
            assert original in row["content"], f"{title}: body not verbatim!"
    print(f"\nVERIFIED: {len(DOCS)} source documents in private:{OFFICE}, "
          "all on-demand, all routed, all byte-identical to the zip.")


if __name__ == "__main__":
    main()
