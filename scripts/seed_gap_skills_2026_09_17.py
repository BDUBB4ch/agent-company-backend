"""Seed the four gap docs found by the 2026-09-17 shelf audit.

Barry: "do the skills, everything" -- and the audit showed the bundled plugin
skills were ALREADY adapted into the office in earlier sessions. What was
genuinely missing:

  business-math-and-checking-the-numbers  -> domain:business_ops  (Amara, Victor)
  selling-wholesale-and-b2b               -> knowledge:commerce   (all business seats)
  writing-real-documents                  -> domain:operations    (Priya, Victor)
  high-level-web-design                   -> domain:creative      (Vivian)
                                             + private:Engineer   (Sophie -- "her or Sophie")

Re-runnable: upserts by (category, source_name), supersedes the old row, never
deletes. Asserts a USE WHEN routing line in the first 1,200 chars (add_fact
prepends a TITLE, so it is not line 1) and the 18,500-char recall ceiling.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))

import memory  # noqa: E402

K = os.path.join(ROOT, "knowledge")
# FILENAMES CARRY THE ROUTING WORDS (2026-09-17, measured). recall._score
# treats the SOURCE_NAME as the title (memory._skill_title), worth 6 per
# matching word, vs 3 per USE WHEN word and up to 5 per word of body
# frequency -- so a long doc's body can outscore a short routing line, and
# retitling the `#` heading changes nothing. The first battery on these four
# went 8/17 with plain names; the fix is the words Barry actually types IN
# THE FILENAME, singular and plural both (recall does no stemming).
PLAN = [
    (os.path.join(K, "business",
                  "business-math-check-the-numbers-number-margin-cost-feeding.md"),
     ["domain:business_ops"]),
    (os.path.join(K, "commerce",
                  "selling-wholesale-b2b-shop-shops-pitch-objections-global-garden-cheaper-terms-order.md"),
     ["knowledge:commerce"]),
    (os.path.join(K, "operations",
                  "writing-real-documents-write-word-doc-spreadsheet-file-desk-print-send-pager.md"),
     ["domain:operations"]),
    (os.path.join(K, "creative",
                  "high-level-web-design-homepage-page-layout-mobile-checkout-hero-landing-wireframe.md"),
     ["domain:creative", "private:Engineer"]),
]
# Earlier names of the same docs, retired on re-seed so two copies never ride.
OLD_NAMES = {
    "business-math-check-the-numbers-number-margin-cost-feeding.md":
        ["business-math-and-checking-the-numbers.md"],
    "selling-wholesale-b2b-shop-shops-pitch-objections-global-garden-cheaper-terms-order.md":
        ["selling-wholesale-and-b2b.md",
         "selling-wholesale-b2b-shop-shops-pitch-objections-terms-order.md"],
    "writing-real-documents-write-word-doc-spreadsheet-file-desk-print-send-pager.md":
        ["writing-real-documents.md"],
    "high-level-web-design-homepage-page-layout-mobile-checkout-hero-landing-wireframe.md":
        ["high-level-web-design.md"],
}


def title_of(text: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return (m.group(1).strip() if m else fallback)[:120]


def main() -> None:
    for path, cats in PLAN:
        fn = os.path.basename(path)
        text = open(path, encoding="utf-8").read().strip()
        assert "USE WHEN:" in text[:1200], f"{fn}: no USE WHEN line in the first 1200 chars"
        assert len(text) <= 18500, f"{fn}: {len(text)} chars -- over the recall ceiling"
        assert len(text) >= 6000, f"{fn}: {len(text)} chars -- too thin"
        for cat in cats:
            with memory.get_db() as conn:
                for old_fn in OLD_NAMES.get(fn, []):
                    n = conn.execute(
                        "UPDATE facts SET status='superseded' WHERE category=? AND "
                        "source_name=? AND status='active'", (cat, old_fn)).rowcount
                    if n:
                        print(f"  {old_fn:<44} {cat:<20} retired old name ({n} row)")
                old = conn.execute(
                    "SELECT id, content FROM facts WHERE category=? AND source_name=? "
                    "AND status='active'", (cat, fn)).fetchall()
                if old and any(r["content"].endswith(text) for r in old):
                    print(f"  {fn:<44} {cat:<20} unchanged, left alone")
                    continue
                for r in old:
                    conn.execute("UPDATE facts SET status='superseded' WHERE id=?", (r["id"],))
            memory.add_fact(cat, text, fn, title=title_of(text, fn[:-3]))
            print(f"  {fn:<44} {cat:<20} {len(text):>6} chars  seeded "
                  f"(superseded {len(old)})")
    # Routing must be VISIBLE to the scorer -- the WHOLE line, not just its
    # start. memory._skill_use_when reads content[:1200] and returns the first
    # USE WHEN line inside that window, cut at the window edge; add_fact
    # prepends a TITLE line above the `#` heading. Measured 2026-09-17: a
    # wrapped line was read as its first physical line only (routing tokens
    # = 0, every battery case failed), and a long heading cut 28 chars off
    # another. "ROUTED" used to mean non-empty; now it means intact.
    print("\nrouting check (whole line must be readable):")
    with memory.get_db() as conn:
        for path, cats in PLAN:
            fn = os.path.basename(path)
            text = open(path, encoding="utf-8").read()
            full = next(l for l in text.splitlines() if l.startswith("USE WHEN:"))[len("USE WHEN: "):]
            for cat in cats:
                row = conn.execute(
                    "SELECT * FROM facts WHERE category=? AND source_name=? AND status='active'",
                    (cat, fn)).fetchone()
                read = memory._skill_use_when(dict(row), 1200) if row else ""
                cut = len(full.rstrip(".")) - len(read)
                state = "whole line read" if read and cut <= 0 else f"CUT BY {cut} CHARS" if read else "NO ROUTING LINE"
                print(f"  {fn[:44]:<44} {cat:<20} {state}")
                assert read and cut <= 0, f"{fn} in {cat}: {state}"
    # Who actually sees each one.
    print("\nvisible to:")
    seen = {}
    for off in ["CIO", "Operations", "BusinessOps", "Legal", "Marketing",
                "Creative", "MovieDirector", "Engineer", "Taliyah"]:
        names = {r.get("source_name") for r in memory.get_active_facts_for_agent(off)}
        for path, _ in PLAN:
            fn = os.path.basename(path)
            if fn in names:
                seen.setdefault(fn, []).append(off)
    for path, _ in PLAN:
        fn = os.path.basename(path)
        print(f"  {fn:<44} {', '.join(seen.get(fn, [])) or 'NOBODY'}")


if __name__ == "__main__":
    main()
