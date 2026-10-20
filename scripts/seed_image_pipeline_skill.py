"""Seed knowledge/character-image-pipeline.md into the brain as a shared skill.

Barry, 2026-08-11: "they need to know how to use everything."

The agents had the canon (WHAT the characters look like) but nothing telling them
HOW images are actually produced -- Kontext vs SDXL, the reference-governs-canon
rule, the two proven failure modes. That knowledge lived only in CLAUDE.md, which
is for Claude, not for them.

source_name ends in .md, so this is a SKILL: it stays off the always-on hot path
and is pulled with read_skill, except where it is pinned. Re-runnable -- supersedes
the previous copy instead of stacking duplicates.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))
import memory

REPO = pathlib.Path(__file__).resolve().parent.parent
SRC = REPO / "knowledge" / "character-image-pipeline.md"
CATEGORY = "knowledge:talia_crew"      # shared -> every agent, same as the canon
SOURCE = "character-image-pipeline.md"


def main() -> None:
    body = SRC.read_text(encoding="utf-8")

    with memory.get_db() as conn:
        cur = conn.execute(
            "UPDATE facts SET status='superseded' "
            "WHERE source_name = ? AND status='active'",
            (SOURCE,),
        )
        if cur.rowcount:
            print(f"superseded {cur.rowcount} previous copy/copies")

    memory.add_fact(CATEGORY, body, source_name=SOURCE)
    print(f"seeded {SOURCE}: {len(body):,} chars -> {CATEGORY}")


if __name__ == "__main__":
    main()
