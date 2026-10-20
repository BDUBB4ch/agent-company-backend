"""Append the word-forms Barry actually types to the USE WHEN lines of the
legal mastery docs (2026-09-08) -- recall has no stemming and drops <3-char
words. Idempotent: only appends tokens not already on line 1."""
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDER = os.path.join(ROOT, "knowledge", "legal")
EXTRA = {
    "advertising-and-claims-law.md": "can we say, can i say, is it ok to say, allowed to say, legal to say, claims, ad claim, marketing claim, copy review, vet this, check this copy, sale, sales, discount, coupon, codes, before it goes out, approve this",
    "cannabis-adjacent-business-law.md": "growers, grow, growing, plants, weed laws, pot, legal in, illegal in, other states, ship to, shipping supplies, processors, banned by stripe, high risk, 280e, paraphernalia law",
    "product-regulation-fertilizer-pesticide-cpsc.md": "fertilizers, nutrients, nutrient label, registered, registration, sell in other states, bionova registration, crop defender 3, fungicide claim, mold, pests, lights, led, tents, safety, recall, warning, california, imports, backpacks",
    "website-terms-privacy-and-accessibility.md": "website legal, site policies, policy page, terms, privacy, data, customer data, tracking, recordings, gdpr, ada lawsuit, accessibility lawsuit, newsletter law, unsubscribe, spam law, texting, sms law, giveaway, contest",
    "contracts-and-supplier-agreements.md": "contracts, agreements, sign, signing, should i sign, paperwork, deal, terms sheet, bionova rights, winter, little green nug, global garden, wholesale customers, sell to shops, reseller, lease, building, landlord, negotiate",
    "intellectual-property.md": "trademarks, register, registration, name is taken, brand protection, copyrights, copied, stole, ai art, ai video, my characters, talia crew, higgsfield rights, elevenlabs, voice rights, licenses, permission to use, logo rights, patents",
    "sales-tax-nexus-and-llc-compliance.md": "taxes, tax, collect tax, charge tax, sales taxes, state tax, city tax, license, licenses, my llc, the llc, entity, company setup, second company, gotcho back llc, pid llc, annual report, filings, deadlines, business license",
    "employment-and-contractors.md": "hire someone, hiring someone, employees, staff, help, part time, payroll, pay someone, contractors, 1099s, freelancers, creator contract, worker, workers, fire someone, let go, wages, hourly",
    "payments-chargebacks-and-platform-terms.md": "chargebacks, disputes, refunds, fraudulent, scam orders, card testing, payments, payment processor, stripe account, paypal account, klarna account, frozen, held funds, banned from, suspended account, marketplace rules, amazon rules, sell on amazon, sell on tiktok",
    "pid-device-odm-and-investor-law.md": "the device, my device, phone, handheld device, factory, manufacturers, china, shenzhen, prototype, investors, investor, raise, raising money, fundraising, shares, equity, valuation, pitch, deck, term sheet, certifications, fcc approval, carriers, privacy claims",
    "disputes-insurance-and-risk.md": "insured, get insurance, business insurance, liability, someone got hurt, hurt, injury, damaged, broken in shipping, lost in shipping, refund fight, threatened, threat, lawyer letter, legal letter, cops, police, subpoenaed, court, judge, risks, biggest risks, protect myself, what if i die",
    "how-marcus-works-legal-method.md": "how do you work, your process, research, look into the law, what does the law say, legal question, legal check, run it by legal, is this allowed, verify this, source for that, cite, citation, real case, made up",
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
