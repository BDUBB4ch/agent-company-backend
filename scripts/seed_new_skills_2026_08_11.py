"""Seed the three new skills Barry asked for on 2026-08-11.

  debugging-discipline.md   -> domain:engineering   (Sophie's seat)
  bdubb-product-shots.md    -> domain:marketing     (Vivian / Derek's seat)
  prop-shot-structure.md    -> knowledge:talia_crew (shared -- Elliot + Vivian both)

All three end in .md, so they are SKILLS: off the always-on hot path, pulled with
read_skill, except where pinned. Re-runnable -- supersedes the previous copy of the
same source_name rather than stacking duplicates.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))
import memory

REPO = pathlib.Path(__file__).resolve().parent.parent

SKILLS = [
    ("knowledge/engineering/debugging-discipline.md", "domain:engineering",
     "debugging-discipline.md"),
    ("knowledge/marketing/bdubb-product-shots.md", "domain:marketing",
     "bdubb-product-shots.md"),
    ("knowledge/prop-shot-structure.md", "knowledge:talia_crew",
     "prop-shot-structure.md"),
    # Added later on 2026-08-11, after Barry asked for the skill-authoring and
    # decision-hygiene patterns to reach the agents too.
    ("knowledge/engineering/writing-agent-skills.md", "domain:engineering",
     "writing-agent-skills.md"),
    ("knowledge/flagging-judgment-calls.md", "knowledge:talia_crew",
     "flagging-judgment-calls.md"),
]


def main() -> None:
    for rel, category, source in SKILLS:
        body = (REPO / rel).read_text(encoding="utf-8")
        with memory.get_db() as conn:
            cur = conn.execute(
                "UPDATE facts SET status='superseded' "
                "WHERE source_name = ? AND status='active'",
                (source,),
            )
            if cur.rowcount:
                print(f"  superseded {cur.rowcount} previous copy of {source}")
        memory.add_fact(category, body, source_name=source)
        print(f"seeded {source:30s} {len(body):>6,} chars -> {category}")


if __name__ == "__main__":
    main()
