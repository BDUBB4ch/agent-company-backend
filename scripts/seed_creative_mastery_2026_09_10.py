"""Seed the creative mastery set (2026-09-10) to Vivian's shelf.

Barry: "now do Vivian, everything she needs." Twelve one-concern reference docs
in knowledge/creative/ land in the NEW `domain:creative` (granted to Creative
only -- Elliot has the film stack, Derek has marketing). On-demand;
re-runnable; oversize docs skipped and named, never aborting the shelf.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))

import memory  # noqa: E402

CATEGORY = "domain:creative"
FOLDER = os.path.join(ROOT, "knowledge", "creative")
NEW = [
    "product-photography-for-ecommerce.md",
    "composition-and-visual-storytelling.md",
    "colour-theory-and-brand-palette.md",
    "typography-logo-and-brand-identity.md",
    "ai-image-generation-on-this-stack.md",
    "social-and-ad-creative-design.md",
    "website-and-store-visual-design.md",
    "packaging-labels-print-and-signage.md",
    "marketing-video-and-motion-design.md",
    "gotcho-back-fashion-and-product-visuals.md",
    "visual-qa-retouching-and-consistency.md",
    "how-vivian-works-creative-director-method.md",
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
                print(f"  {fn:<48} {len(text):>6} chars  OVER BUDGET -- skipped, trim it")
                skipped.append(fn)
                continue
            old = conn.execute(
                "SELECT id, content FROM facts WHERE category=? AND source_name=? AND status='active'",
                (CATEGORY, fn)).fetchall()
            if old and any(r["content"].endswith(text.strip()) for r in old):
                skipped.append(fn)
                print(f"  {fn:<48} {len(text):>6} chars  (already seeded, unchanged)")
                continue
            for r in old:
                conn.execute("UPDATE facts SET status='superseded' WHERE id=?", (r["id"],))
            total += len(text)
            print(f"  {fn:<48} {len(text):>6} chars  (superseded {len(old)} old row(s))")
    for fn in present:
        if fn in skipped:
            continue
        text = open(os.path.join(FOLDER, fn), encoding="utf-8").read()
        memory.add_fact(CATEGORY, text, fn, title=title_of(text, fn[:-3]))
    print(f"seeded {len(present) - len(skipped)} docs, {total:,} chars, to {CATEGORY}")

    memory.grant_domain_access("Creative", "creative")
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT source_name, LENGTH(content) n FROM facts "
            "WHERE category=? AND status='active' ORDER BY source_name", (CATEGORY,)).fetchall()
    live = {r["source_name"]: r["n"] for r in rows}
    print(f"\n{CATEGORY} now holds {len(rows)} active docs, "
          f"{sum(live.values()):,} chars")
    for fn in NEW:
        if fn in live:
            uw = memory._skill_use_when(
                {"source_name": fn, "content": open(os.path.join(FOLDER, fn), encoding="utf-8").read()},
                max_len=1200)
            print(f"  {fn:<48} {live[fn]:>6}  routing {len(uw or ''):>4} chars")
        else:
            print(f"  {fn:<48}  NOT LIVE")


if __name__ == "__main__":
    main()
