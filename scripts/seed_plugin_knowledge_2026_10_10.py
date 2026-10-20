"""Seed the 52 knowledge files adapted 2026-10-10 from the knowledge-work plugins (sales, customer-support,
brand-voice, human-resources, enterprise-search, productivity, product-management, intuit-quickbooks, finance, data,
legal, canva, figma, small-business leftovers). Barry: "turn them all into skills". Folder name = domain.
Same supersede-then-add logic as _seed_knowledge.py; safe to re-run after an edit."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import memory

FILES = {'business_ops': ['bill-payment-run-proposal.md', 'bills-intake-coding-and-matching.md', 'books-first-close-and-tax-chain.md', 'saved-reports-and-report-pack.md', 'audit-ready-books-and-spot-checks.md', 'business-health-briefing.md', 'check-an-analysis-before-sharing.md', 'csv-export-recipes-and-data-dictionary.md', 'loan-and-credit-line-questions.md', 'overdue-invoice-chase.md', 'payroll-cost-and-first-hire-pay.md', 'quote-or-invoice-from-an-email.md'], 'creative': ['brand-check-and-acting-on-feedback.md', 'resizing-one-design-for-every-format.md', 'slide-decks-diagrams-and-graphic-motion.md'], 'leadership': ['customer-research-synthesis-for-product-decisions.md', 'product-brainstorming-sparring-partner.md', 'product-competitive-comparison-and-trend-calls.md', 'product-line-metrics-review.md', 'product-roadmap-and-weekly-work-plan.md', 'product-spec-for-a-new-product-or-line.md', 'status-updates-to-barry-and-decision-records.md'], 'legal': ['contract-red-flags-quick-read.md', 'agreements-on-file-and-signing-checklist.md', 'legal-brief-and-incident-response.md'], 'marketing': ['account-health-and-reorder-radar.md', 'b2b-buyer-research-and-call-prep.md', 'brand-voice-discovery-and-tone-flex.md', 'competitor-in-the-conversation.md', 'customer-inbox-triage-and-digest.md', 'customer-reply-drafts-and-refund-calls.md', 'customer-research-and-escalation-packets.md', 'deal-review-and-close-plan.md', 'drafting-sales-emails-and-replies.md', 'expansion-and-upsell-whitespace.md', 'objection-handling-in-the-moment.md', 'outreach-drafts-slop-test-and-sequences.md', 'pipeline-tracker-and-follow-up-queue.md', 'prospect-list-icp-and-scoring.md', 'sales-pipeline-forecast-and-weekly-wrap.md', 'sell-sheets-and-sales-one-pagers.md', 'store-faq-and-help-articles.md', 'win-loss-and-customer-voice.md'], 'operations': ['catch-up-digest-and-open-loop-sweep.md', 'first-hire-pay-range-and-offer-package.md', 'grants-and-formal-solicitations-go-no-go.md', 'org-planning-first-hires-and-people-numbers.md', 'payroll-prep-for-a-first-hire.md', 'performance-reviews-and-policies-for-a-first-hire.md', 'screening-applicants-with-a-rubric-and-job-post.md', 'searching-what-the-office-already-knows.md', 'written-quotes-and-proposals.md']}

memory.init_db()
n = 0
for domain, names in FILES.items():
    category = f"domain:{domain}"
    for name in names:
        with open(os.path.join(ROOT, "knowledge", domain, name), "r", encoding="utf-8") as f:
            content = f.read()
        with memory.get_db() as conn:
            conn.execute(
                "UPDATE facts SET status = 'superseded' WHERE category = ? AND source_name = ? AND status = 'active'",
                (category, name),
            )
        memory.add_fact(category, content, name)
        n += 1
print(f"Seeded {n} files")
