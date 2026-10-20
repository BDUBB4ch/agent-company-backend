"""Add the word-forms Barry actually types to the USE WHEN lines of the
marketing mastery docs (2026-09-08). recall._tokens does no stemming and drops
words under 3 chars, so "emails" != "email" and "ad" vanishes; measured on a
14-ask battery: 9/14 routed right before this. Idempotent: only appends tokens
that are not already on line 1."""
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDER = os.path.join(ROOT, "knowledge", "marketing")
EXTRA = {
    "email-marketing-mastery.md": "emails, spam, spam folder, inbox, bounces, bounce rate, blast, campaign, campaigns, flows, automations, omnisend, email cta, email button, landing in spam, not delivered",
    "calls-to-action.md": "ctas, buttons, button copy, button wording, cta wording, cta ideas, what to say at the end, closing line, ask them to, get them to click, link text, book now, order now",
    "ad-creative-mastery.md": "ads, ad ideas, ad concepts, concepts, ad variants, creatives, creative ideas, ad campaign creative, ad image, ad video, ad script, banner ad, ad mockup, ad for, ads for",
    "conversion-rate-optimization.md": "clicks, orders, no orders, zero orders, not converting, conversions, visitors, traffic but no sales, people leave, abandon, checkout problems, sales page",
    "retention-loyalty-and-ltv.md": "repeat purchase rate, repeat customers, repeat buyers, reorders, old customers, past customers, come back, bring them back, customer lifetime, loyalty program, rewards program",
    "marketing-analytics-and-attribution.md": "numbers, rates, results, performance, telling us, working or not, data, stats, statistics, benchmark, benchmarks, track, tracking, measure",
    "customer-acquisition-and-prospecting.md": "customers, more customers, more sales, grow the business, wholesale accounts, shops, retailers, distributors, hunting, hunter, prospect list, cold outreach, get customers",
    "social-media-platform-playbook.md": "socials, social platforms, platforms, which platform, social strategy, social plan, social content",
    "paid-ads-playbook.md": "ads, run ads, paid, advertising, ad budget, bidding, keywords, negative keywords, search ads, campaigns, ad account",
    "seo-and-ai-search.md": "rank, ranking, rankings, search results, organic, organic traffic, blog, blogs, content strategy, google ranking, bing ranking",
    "copywriting-and-persuasion.md": "product descriptions, descriptions, write copy, write the copy, caption copy, email copy, wording, phrasing, persuasive, convince",
    "brand-strategy-and-positioning.md": "brand strategy, our brand, position, positioned, stand out, different from, compete with, competitors",
    "community-influencers-and-partnerships.md": "influencers, creators, partners, collabs, collaborations, communities, groups, sponsorships, affiliates, ambassadors",
    "marketing-compliance-and-platform-rules.md": "allowed to, can we say, can i say, is it ok to, legal to, rules, policies, get banned, banned, restricted, flagged, rejected, disapproved",
    "short-form-video-and-content-creation.md": "videos, reels, shorts, content, content ideas, post ideas, film, filming, shoot, shooting, photos, product photos, content calendar",
}


def main() -> None:
    for fn, extra in EXTRA.items():
        path = os.path.join(FOLDER, fn)
        if not os.path.isfile(path):
            print(f"  skip {fn} (not on disk yet)"); continue
        lines = open(path, encoding="utf-8").read().split("\n")
        assert lines[0].startswith("USE WHEN:"), fn
        have = {t.strip().lower() for t in lines[0][len("USE WHEN:"):].split(",")}
        add = [t.strip() for t in extra.split(",") if t.strip().lower() not in have]
        if not add:
            print(f"  {fn}: nothing to add"); continue
        lines[0] = lines[0].rstrip().rstrip(",") + ", " + ", ".join(add)
        assert len(lines[0]) < 1100, f"{fn}: routing line too long for the 1,200-char scan"
        tmp = path + ".tmp"
        open(tmp, "w", encoding="utf-8").write("\n".join(lines))
        os.replace(tmp, path)
        print(f"  {fn}: +{len(add)} tokens (line now {len(lines[0])} chars)")


if __name__ == "__main__":
    main()
