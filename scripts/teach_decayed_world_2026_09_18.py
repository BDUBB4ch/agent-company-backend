"""Barry's Decayed World hyper-realism reference -> the three seats that make pictures.

Barry, 2026-09-18: "give these to who it matters." Amara (she makes her own),
Vivian (creative director, the office's image craft) and Elliot (film).

Stored VERBATIM with an office note on top saying which parts apply to which
engine -- his words are never edited, and the negative block / weight syntax /
"14K 300dpi" would otherwise be used wrong on our local engines.

Re-runnable: ingest.teach upserts by title slug.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import ingest  # noqa: E402
import memory  # noqa: E402

TITLE = ("decayed-world-hyper-realistic-intricate-decay-rust-ruins-"
         "apocalyptic-artist-reference")
DOC = os.path.join(os.path.dirname(__file__), "..",
                   "knowledge", "decayed-world-reference.md")
OFFICES = ["BusinessOps", "Creative", "MovieDirector"]


def main() -> None:
    with open(DOC, encoding="utf-8") as fh:
        text = fh.read()

    want = next(l for l in text.splitlines() if l.startswith("USE WHEN:"))

    for office in OFFICES:
        print(ingest.teach(office, "knowledge", text, title=TITLE))

        facts = {f.get("source_name"): f
                 for f in memory.get_active_facts_for_agent(office)}
        key = next((k for k in facts if k and "decayed-world" in k), None)
        assert key, f"{office}: fact not found after teach"
        got = memory._skill_use_when({"content": facts[key]["content"]}, 1200)
        assert got, f"{office}: USE WHEN not readable in first 1200 chars"
        assert len(got) >= len(want.removeprefix("USE WHEN:").strip()) - 5, \
            f"{office}: routing line cut short ({len(got)})"

        # His fifteen prompts must arrive whole -- this doc's whole value is
        # that it is his words, so count them rather than trusting the write.
        body = facts[key]["content"]
        for n in range(1, 16):
            assert f"### **{n}." in body, f"{office}: prompt {n} missing"
        print(f"   ok {office}: {len(body)} chars, 15/15 prompts, "
              f"routing {len(got)} chars")


if __name__ == "__main__":
    main()
