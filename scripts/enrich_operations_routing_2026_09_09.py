"""Append typed word-forms to the USE WHEN lines of the operations docs
(2026-09-09). Idempotent."""
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDER = os.path.join(ROOT, "knowledge", "operations")
EXTRA = {
    "executive-assistant-and-chief-of-staff-method.md": "whats on my plate, my plate, whats waiting, waiting on me, what needs me, pending on me, my priorities, focus, handle my day, run my day, keep me on track, remind me, nagging, decisions for me, ready for me",
    "delegation-and-briefing-craft.md": "delegating, delegated, briefing, briefed, hand this to, give it to, pass it to, assign this, team, teammates, specialists, amara should, marcus should, derek should, sophie should, vivian should, elliot should, whos on it, working on it, board status",
    "research-method-for-business-questions.md": "researching, looked into, find info, information on, details on, background on, learn about, what do you know about, whats the best, best option, options, alternatives, pricing research, competitor prices, check the facts, is that true",
    "task-and-project-management-for-a-solo-founder.md": "projects list, project list, my projects, whats in progress, in progress, backlog, plan, planning, milestone, done, finished, complete, tracking, tracker, priorities, prioritize, prioritise",
    "store-operations-and-sops.md": "orders, order, ship it, shipped, shipping today, fulfil, packaging, boxes, labels, tracking numbers, stock, restock, received, inventory arrived, return, returns, refunds, procedures, how do we handle, routine, checklists, if i am away, out of town",
    "customer-service-excellence.md": "email from a customer, customer asked, customer wants, someone asked, they asked, reply, respond, response, answer them, write back, template, templates, refund them, replace it, reviews, review, complaint email, angry email, support email, help them",
    "communication-and-meeting-craft.md": "update me, catch me up, recap, rundown, report back, summary, in short, short version, brief version, draft, drafts, write to, email to, message to, letter, tone check, say it better, meeting prep, prep me, talking points",
    "calendar-time-and-priority-management.md": "week, weekly, month, monthly, plan, planning, schedule me, book, booked, free time, busy, availability, due date, due dates, upcoming, coming up, this week, next week, whats due, seasonal plan, holiday, holidays, cutoffs",
    "vendor-and-partner-coordination.md": "vendor contact, supplier email, email the supplier, ask the supplier, order from, reorder from, our suppliers, our vendors, accounts, account renewals, renew, cancel subscription, partner meeting, prep for the call, follow up email, vendor issue, supplier problem, late order, wrong order",
    "knowledge-management-and-the-business-brain.md": "remember, remembers, memory, forget, forgot, store this, log this, note this, record this, keep track, brain, brains, facts, fact, knowledge gaps, what is missing, whats missing, missing info, update the business brain, voice file, my voice",
    "hiring-and-onboarding-operations.md": "hire someone, hiring someone, employee, employees, staff, help wanted, job posting, post a job, interviews, interviewing, applicant, onboarded, train, training plan, first day, new person, assistant, part-time, part time, contractor",
    "how-priya-works-operations-method.md": "handle it, deal with it, sort it out, take care of this, make it happen, get it done, on it, run with it, coordinate this, manage this, what happens now, next steps, whats the plan, your plan, how will you",
}
for fn, extra in EXTRA.items():
    path = os.path.join(FOLDER, fn)
    if not os.path.isfile(path):
        print(f"  skip {fn}"); continue
    lines = open(path, encoding="utf-8").read().split("\n")
    assert lines[0].startswith("USE WHEN:"), fn
    have = {t.strip().lower() for t in lines[0][len("USE WHEN:"):].split(",")}
    add = [t.strip() for t in extra.split(",") if t.strip().lower() not in have]
    if not add:
        print(f"  {fn}: nothing to add"); continue
    lines[0] = lines[0].rstrip().rstrip(",") + ", " + ", ".join(add)
    assert len(lines[0]) < 1100, fn
    tmp = path + ".tmp"; open(tmp, "w", encoding="utf-8").write("\n".join(lines)); os.replace(tmp, path)
    print(f"  {fn}: +{len(add)} (line {len(lines[0])} chars)")
