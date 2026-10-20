"""Load the 2026-09-26 adopted skill docs into the brain (Barry: "go" on the adoption list).

Sources (docs only -- no installers, no API keys): NewsJack PR method (MIT), Anthropic knowledge-work-plugins
small-business + brand-voice (Apache-2.0), anthropics/financial-services variance/accrual (Apache-2.0),
addyosmani/agent-skills (MIT). Spec: knowledge/ADOPTION_SPEC_2026-09-26.md.

SHELVES (categorize everything, scope by capability):
  knowledge/pr/*          -> domain:pr          NEW shelf, granted to Marketing (Derek) + Operations (Priya) only
  knowledge/finance/*     -> domain:business_ops (Amara, Victor)
  knowledge/marketing/*   -> domain:marketing    (Derek, Vivian, Ilnora) -- only the files listed below
  knowledge/operations/*  -> domain:operations   (Priya, Victor)
  knowledge/engineering/* -> domain:engineering  (Sophie)
On-demand skills (source_name ends .md). Re-running supersedes the old copy, never stacks duplicates.
"""
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import memory  # noqa: E402

K = os.path.join(ROOT, "knowledge")
FILES = {
    "domain:pr": sorted(glob.glob(os.path.join(K, "pr", "*.md"))),
    "domain:business_ops": [os.path.join(K, "finance", f) for f in (
        "cash-flow-snapshot.md", "month-end-prep.md", "inventory-planner.md", "restock-decisions.md",
        "tax-season-organizer.md", "variance-commentary.md", "accrual-schedule.md")],
    "domain:marketing": [os.path.join(K, "marketing", f) for f in (
        "ad-performance-review.md", "seo-and-ai-visibility-fixes.md", "review-reputation.md",
        "content-strategy.md", "brand-voice-guidelines.md")],
    "domain:operations": [os.path.join(K, "operations", "monday-brief.md")],
    "domain:engineering": [os.path.join(K, "engineering", f) for f in (
        "code-review-deep.md", "doubt-driven-self-check.md", "security-hardening.md")],
}
PR_SEATS = ("Marketing", "Operations")


def main() -> None:
    with memory.get_db() as conn:
        for seat in PR_SEATS:
            if not conn.execute("SELECT 1 FROM agent_domains WHERE office_name=? AND domain='pr'", (seat,)).fetchone():
                conn.execute("INSERT INTO agent_domains (office_name, domain) VALUES (?, 'pr')", (seat,))
                print(f"granted shelf 'pr' to {seat}")
    n = 0
    for cat, paths in FILES.items():
        for path in paths:
            name = os.path.basename(path)
            if not os.path.exists(path):
                print(f"MISSING {path}")
                continue
            text = open(path, encoding="utf-8").read().strip()
            lines = text.splitlines()
            if len(lines) < 2 or not lines[1].startswith("USE WHEN:"):
                print(f"BAD FORMAT {name} (line 2 must be USE WHEN:) -- skipped")
                continue
            with memory.get_db() as conn:
                old = conn.execute("UPDATE facts SET status='superseded' WHERE source_name=? AND status='active'",
                                   (name,)).rowcount
            memory.add_fact(cat, text, source_name=name)
            n += 1
            print(f"loaded {name:40s} -> {cat:22s} {len(text):>6,} chars" + (f" (superseded {old})" if old else ""))
    print(f"total loaded: {n}")


if __name__ == "__main__":
    main()
