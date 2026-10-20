"""Append typed word-forms to the USE WHEN lines of the leadership docs
(2026-09-09). Idempotent."""
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDER = os.path.join(ROOT, "knowledge", "leadership")
EXTRA = {
    "ceo-operating-system.md": "run things, how you run, running things, whats the priority, priority, top three, focus on, whats important, whats next for the company, company update, state of things, where are we, weekly plan, quarterly plan, plan for the quarter, your rhythm",
    "strategy-and-competitive-positioning.md": "beat, compete, competing, competitor, our edge, advantage, differentiate, stand out, niche, specialize, specialise, general store, expand into, get into, market share, own the market, the plan long term, five year, next year, hydro market",
    "decision-making-and-judgment.md": "choose, choice, choices, pick, which one, which is better, better option, go or no go, yes or no, thoughts, opinion, your opinion, what do you think, advise, advice, sanity check, am i wrong, am i crazy, talk me out of, gut, instinct",
    "growth-strategy-for-a-small-ecommerce-brand.md": "sales are dead, sales are slow, nothing is selling, no orders, stuck, plateau, flat, grow faster, double sales, 10k a month, revenue goal, sales goal, first customers, more orders, customers back, retention, wholesale idea, storefront idea",
    "leading-the-team.md": "the crew, everyone, the others, teammates, priya, amara, marcus, derek, vivian, sophie, elliot, is doing good work, doing bad work, messed up, slacking, review their work, quality of work, whos responsible, get them to, make sure they, they should",
    "partnerships-alliances-and-supplier-strategy.md": "supplier, suppliers, our supplier, the distributor, bionova people, winters deal, the deal with winter, global gardens, relationship with, partner with, team up, work with another company, collab, joint, agreement with, rights, us rights, selling rights",
    "risk-and-crisis-management-for-the-ceo.md": "problem, big problem, screwed, disaster, fire, fires, put out fires, blew up, went bad, fallout, cover, protect the business, safeguard, safe, insurance question, what if we lose, what if they, plan b, fallback, worst that could happen",
    "financial-literacy-for-the-ceo.md": "afford, can we afford, money situation, how are we doing financially, financially, bottom line, making money, losing money, in the red, in the black, cash flow, the books, amaras numbers, what amara said, allocate money, where to put money, spend money on, cost us",
    "market-and-customer-insight.md": "buyers, shoppers, audience, our people, the growers, hobbyists, commercial growers, other shops, why they buy, what they want, what they need, pain points, complaints, what people say, what customers say, research the market, size of the market, opportunity, opportunities",
    "pid-venture-strategy.md": "pid device, pid company, pid business, the phone, privacy handheld, device startup, hardware startup, launch pid, build the device, make the device, pid next steps, pid roadmap, pid investors, pid odm, pid partners, when do we start pid, pid timeline",
    "how-victor-works-ceo-method.md": "handle it, deal with it, take care of it, make it happen, on it, run with it, sort it, manage this, whats your move, what would you do first, first move, where do we start, start with, whats the play",
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
