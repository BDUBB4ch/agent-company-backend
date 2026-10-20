"""Give every reference skill a USE WHEN routing line, so recall stops guessing.

2026-08-16, Barry: "i dont want then to have to dig through shit to find
what they are looking for... so they know where to look, and read it fast."

State before this: 104 of 123 on-demand documents had NO routing line, so
recall.py could only reach them by body keyword matching -- fuzzy, and it
pulls big documents on generic words, which costs both accuracy AND speed
(a wrongly-recalled 50K doc is 12K tokens of prompt Barry waits for).

SCOPE, deliberately narrow: only Claude/plugin-authored REFERENCE skills
are edited here. Barry's own authored canon, scripts and story docs are
NEVER touched -- they get identical routing power from
recall.ROUTING_OVERRIDES instead, which leaves the files byte-identical.

Dry-run by default; --apply to commit. Re-runnable: skips any doc that
already has a USE WHEN line.
"""

import os
import sqlite3
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "brain.db")

# source_name (without .md) -> routing line, written in BARRY'S vocabulary
# rather than librarian labels: routing only fires on words he'd actually
# type. Kept under 200 chars (memory._skill_use_when caps there).
LINES = {
    # -- marketing ------------------------------------------------------
    "viral-hooks": "writing a hook, caption, opener or scroll-stopper for social -- what makes a post get watched, shared or saved",
    "campaign-plan": "planning a marketing campaign -- channels, calendar, budget, offers, what we run and when",
    "performance-report": "reporting on marketing results -- what worked, opens clicks conversions, campaign performance",
    "brand-promo-style": "the look and voice of a promo -- brand style for ads, banners, promo graphics",
    "brand-review": "checking whether something is on brand -- voice, colours, logo use, does this look like us",
    "ux-copy": "writing the words inside a page, button, form or banner -- microcopy, labels, error messages",
    "seo-audit": "search rankings and site SEO -- keywords, titles, meta descriptions, why we don't rank",
    "email-sequence": "building a series of emails -- welcome flow, abandoned cart, reorder reminders, drip",
    "content-creation": "making content -- posts, blogs, video scripts, what to publish",
    "competitive-brief": "sizing up a competitor -- what they sell, how they price, where we win",
    # -- business / finance ---------------------------------------------
    "tax-fundamentals": "taxes -- quarterly estimates, deductions, self employment tax, sales tax nexus, 1099s, what to set aside",
    "competitive-strategy": "strategy against competitors -- positioning, pricing power, moats, where to compete",
    "variance-analysis": "why the numbers moved -- budget vs actual, this month vs last, what changed and why",
    "financial-statements": "P&L, balance sheet, cash flow -- reading or building the actual statements",
    "business-finance-and-taxes": "margins, landed cost, cash flow vs profit, break even, CAC and LTV, plus small business taxes",
    "product-sourcing-and-dropshipping": "finding a supplier or product -- wholesale, dropshipping, private label, alibaba, landed cost",
    "supplier-scam-red-flags": "is this supplier or offer legit -- scam warning signs, payment weirdness, vetting a vendor",
    "product-research": "researching a product before selling it -- demand, competition, margins, is it worth carrying",
    # -- legal ----------------------------------------------------------
    "contract-review": "reviewing a contract or agreement -- terms, clauses, what to redline, what we're signing",
    "compliance-check": "is this allowed -- regulations, required disclosures, approvals before we launch or advertise",
    "legal-risk-assessment": "how bad is this legally -- severity, likelihood, exposure, when to get a real lawyer",
    "nda-triage": "an NDA came in -- can we sign it, what's non standard, does it need review",
    # -- engineering ----------------------------------------------------
    "prompt-engineering": "writing a TEXT prompt for an AI model or agent -- system prompts, instructions, tool definitions (NOT image prompts)",
    "deploy-checklist": "shipping a change -- what to check before and after deploying",
    "code-review": "reviewing code -- bugs, correctness, style, what to flag",
    "system-design": "designing how a system fits together -- architecture, components, trade offs",
    "testing-strategy": "how to test something -- what to cover, unit vs integration, what could break",
    "tech-debt": "messy code or shortcuts piling up -- what to clean up and in what order",
    "incident-response": "something is broken right now -- triage, diagnose, fix, write it up after",
    # -- design ---------------------------------------------------------
    "design-critique": "judging a design or image -- is it good, what's off, how to make it stronger",
    "accessibility-review": "can people actually read and use this -- contrast, text size, colour blindness, legibility on imagery",
    "design-system": "keeping one consistent visual language -- colours, type, spacing, components across the brand",
    "design-handoff": "handing a design over to be built -- specs, assets, what the developer needs",
    "research-synthesis": "making sense of customer feedback in bulk -- reviews, surveys, finding the themes",
    "user-research": "learning what customers actually want -- interviews, surveys, questions to ask them",
    # -- knowledge ------------------------------------------------------
    "email-marketing-bdubb": "email marketing for b dubb -- omnisend, the list, signup offers BIG15 BIG10, what to send and to whom",
    "video-directing": "directing a video -- shots, coverage, pacing, how to shoot a sequence",
    "revenue-levers": "how to actually make more money here -- the six named levers, reorders, attach rate, the $200 threshold",
    "pid-founder-bible": "PID and piddevice.com -- the sovereign privacy handheld, its positioning, unit economics, ODM partners",
    "pid-guardrails": "rules for talking about PID -- what can and cannot be claimed, keeping PID separate from the other businesses",
    "image-prompting-basics": "writing an image prompt -- diffusion prompt structure, negatives, what SDXL can and can't do",
}


def add_line(text: str, line: str) -> str | None:
    if "USE WHEN:" in text[:1200]:
        return None
    lines = text.split("\n")
    at = 1 if lines and (lines[0].startswith("#") or len(lines[0]) < 120) else 0
    return "\n".join(lines[:at] + ["", f"USE WHEN: {line}", ""] + lines[at:])


def main(apply: bool):
    conn = sqlite3.connect(DB)
    changed = skipped = missing = 0
    for stem, line in sorted(LINES.items()):
        rows = conn.execute(
            "SELECT id, source_name, content FROM facts "
            "WHERE status='active' AND (source_name=? OR source_name=?)",
            (f"{stem}.md", f"{stem}/SKILL.md")).fetchall()
        if not rows:
            missing += 1
            print(f"  (not in this brain): {stem}")
            continue
        for fid, source, content in rows:
            updated = add_line(content, line)
            if updated is None:
                skipped += 1
                continue
            changed += 1
            print(f"  {'UPDATE' if apply else 'would update'}  fact {fid:<5} {source}")
            if apply:
                conn.execute("UPDATE facts SET content=? WHERE id=?", (updated, fid))
    if apply:
        conn.commit()
    conn.close()
    print(f"\n{'applied' if apply else 'dry run'}: {changed} updated, "
          f"{skipped} already had a line, {missing} not present")


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
