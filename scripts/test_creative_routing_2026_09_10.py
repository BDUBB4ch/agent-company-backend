"""Does recall put the right creative doc in front of Vivian?

Behaviour test, not a unit test: it runs the real recall scorer against her
real shelf and asserts which doc comes back for phrasings Barry would type.
Run after ANY edit to a USE WHEN line in knowledge/creative/.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import agents   # noqa: E402
import recall   # noqa: E402

OFFICE = "Creative"
PINNED = agents.PINNED_SKILLS.get(agents.CREATIVE_ID, [])

CREATIVE_PREFIXES = (
    "Product Photo", "Composition", "Colour", "Color", "Typography",
    "AI Image", "Social", "Website", "Packaging", "Marketing Video",
    "Gotcho", "Visual QA", "How ", "Creative Director",
)

# message -> a word that must appear in the title of a recalled doc
CASES = [
    ("i need a product shot of the silution bottle", "photograph"),
    ("shoot the grow tents on white background", "photograph"),
    ("this banner looks cluttered, where should the bottle go", "composition"),
    ("what hex should the button be, the orange looks wrong", "colour"),
    ("do we need a new logo or just a cleanup", "logo"),
    ("which model should i render this on", "image"),
    ("what size is an instagram story and where is the safe zone", "social"),
    ("the homepage hero looks bad on my phone", "website"),
    ("i want bottle labels printed, what do they need on them", "label"),
    ("make a short product video for tiktok", "video"),
    ("we need photos for the hemp backpacks", "gotcho"),
    ("check this render, something looks off about it", "qa"),
    ("where do we start on the visuals this week", "how-vivian-works"),
]

QUIET = ["morning", "how are you doing today", "thanks, that works"]


def titles_for(message: str) -> list[str]:
    _block, titles = recall.recall_for_message(OFFICE, message, pinned_titles=PINNED)
    return titles


def main() -> None:
    fails = []
    for msg, want in CASES:
        titles = titles_for(msg)
        ok = any(want.lower() in t.lower() for t in titles)
        print(f"{'PASS' if ok else 'FAIL'}  {msg!r}\n        -> {titles or '(nothing)'}")
        if not ok:
            fails.append(msg)
    for msg in QUIET:
        titles = titles_for(msg)
        noisy = [t for t in titles if t.startswith(CREATIVE_PREFIXES)]
        ok = not noisy
        print(f"{'PASS' if ok else 'FAIL'}  (quiet) {msg!r} -> {noisy or 'nothing'}")
        if not ok:
            fails.append(msg)
    print()
    if fails:
        print(f"{len(fails)} FAILING")
        raise SystemExit(1)
    print(f"creative routing battery: ALL PASS ({len(CASES) + len(QUIET)} cases)")


if __name__ == "__main__":
    main()
