"""Condense seedance-prompting -- Barry, 2026-08-15: "condense it some how
without losing the information. this skill needs to be good."

Nothing is lost. Every section removed here exists in FULL in
seedance-production-tasks, which Elliot now carries pinned alongside it. This
only stops him holding two copies of the same rules in one window.

  LOCKED vs UNLOCKED, STORYBOARD vs KEYFRAMES, 3D CLAY-MODEL PREVIZ,
  Mode-dependent parameter locks, the asset-spec numbers  ->  production-tasks
  CINEDANCE 12-block order  ->  superseded by THE BLEND table (kept there)
  IRON RULE + Negative prompting  ->  merged, they argued the same point twice

Re-runnable: exits clean if already condensed.
"""
import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parent.parent / "knowledge" / "seedance-prompting.md"
DROP = [
    "LOCKED vs UNLOCKED",
    "STORYBOARD vs KEYFRAMES",
    "3D CLAY-MODEL PREVIZ",
    "Mode-dependent parameter locks",
    "CINEDANCE",
]
POINTER = """## Task types, parameter locks, storyboards, blockouts, editing

All of it lives in **seedance-production-tasks**, pinned next to this one -- task types and
their trigger words, what locks aspect ratio and duration, `omni_reference_task_type`, the
error codes, first/last frames vs keyframes vs storyboard grids vs blockouts, editing,
extension, one-click, transitions, and every asset spec that errors. Go there the moment the
job is anything other than writing a fresh shot.

"""


def main() -> None:
    t = SRC.read_text(encoding="utf-8")
    before = len(t)
    if "Task types, parameter locks, storyboards, blockouts, editing" in t:
        print("already condensed")
        return

    parts = re.split(r"^(## .+)$", t, flags=re.M)
    out = [parts[0]]
    for i in range(1, len(parts), 2):
        head, body = parts[i], parts[i + 1]
        if any(d in head for d in DROP):
            continue
        out.append(head + body)
    t = "".join(out)

    # The pointer replaces all five, sitting where the first one was.
    t = t.replace("## The four-part skeleton", POINTER + "## The four-part skeleton", 1)

    SRC.write_text(t, encoding="utf-8")
    print(f"seedance-prompting {before:,} -> {len(t):,} chars ({len(t)-before:+,})")


if __name__ == "__main__":
    main()
