"""Build the Business Brain file the Starter Brain system runs on.

Barry, 2026-08-29: "she needs to know this as intended by the zip." The zip's
README: "Those two files are the whole system. The skills are just how Claude
uses them." Priya held all six workflows and neither file.

This is the FIRST of the two. Every line below is drawn from what the office
already has on record (CLAUDE.md + the facts store) -- the skill's own
instruction is "offer a first draft based on what they have already told you
and let them correct it. A corrected draft beats a blank field."

NOTHING HERE IS INVENTED. Where the office genuinely does not know, the line
says [ASK BARRY] instead of guessing -- same discipline as his canon.

ALWAYS-ON (source_name has no .md) because the zip intends it to govern every
reply without being asked. Kept tight for that reason; the deep detail already
lives in the shared business facts.

Re-runnable: upserts by source_name.
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
import memory  # noqa: E402

CATEGORY = "private:Operations"
SOURCE = "business-brain"

CONTENT = """BUSINESS BRAIN -- BARRY'S MASTER CONTEXT (Starter Brain file 1 of 2)

DRAFT, 2026-08-29. Assembled by Claude from what this office already has on
record -- not from an interview. Barry corrects it; every [ASK BARRY] line is
a real gap, not a guess. Apply this to every task without being asked.

== WHO HE IS ==
Barry White. Three ventures, and PID NEVER mixes with the other two:
- B DUBB GROWS LLC -- the money-maker. Indoor/hydroponic growing supplies,
  Colorado Springs, bdubbgrowsllc.com (WooCommerce). He is a grower and
  breeder himself; that is why the voice works.
- GOTCHO BACK -- backpack brand. [ASK BARRY: voice, customer and offers are
  still undocumented.]
- PID / piddevice.com -- sovereign privacy-first Linux handheld, pre-hardware,
  seeking an ODM partner. Never routed through marketing platforms; partner
  outreach goes 1:1 from Titan mail.

== WHO B DUBB SERVES ==
Real growers, all crops INCLUDING cannabis -- he grows and breeds, and the
audience is not hobby-gardener-only. Channel exclusions are about the
PLATFORM, never the grower: no cannabis in Google Ads copy or WooCommerce
product descriptions (product copy feeds Google Shopping). Cannabis in email
is fine on Omnisend. SMS is restricted everywhere (carrier rules, by business
category, not by message).
[ASK BARRY: the exact words his customers use, and what makes them tune out.]

== WHAT HE SELLS ==
- BIONOVA nutrient line -- the profit engine and the recurring-revenue lever.
  ~55-60% gross margin. He is the OFFICIAL US SOURCE (never say "exclusive").
  Winter / The Little Green Nug is the US distributor; Barry holds US selling
  rights and a standing 40%-under-wholesale cost that nobody else has.
- Everything else (hardware, EH, GHF lines etc.) -- from Global Garden at
  regular wholesale, 10-35% margins. Traffic and filler, not the profit play.
  Global Garden is an ACTIVE supplier: handle with care, never disparage.
- Free entry point: the signup popup. BIG15 = 15% off the Bionova line,
  BIG10 = 10% off everything else. No minimum, first order, and they CANNOT
  be combined -- say so wherever the codes appear. Free shipping over $200 is
  a separate lever.
- Path free to paid: popup signup -> welcome email with both codes -> first
  order -> replenishment.

== DREAM CLIENT / BAD FIT ==
[ASK BARRY -- not recorded anywhere. Lead triage needs one sentence each.]

== HOW HE SOUNDS ==
Grower-to-grower. Two modes: technical when the reader is technical,
approachable when they are not. No corporate register.
Brand colors: #FF7900 accent only, #008903, #47704C body.
The VOICE DNA FILE DOES NOT EXIST YET -- capturing it is Priya's job and it is
the single biggest gap in this office's writing. Until it exists, write plainly
and never use: delve, unlock, elevate, revolutionize, seamless, robust,
cutting-edge, supercharge, game-changer, leverage as a verb, streamline,
empower -- or any sentence shaped "this isn't X, it's Y."

== RULES OF OPERATION (hard) ==
- NOTHING acts without his approval. No auto-publishing, auto-sending or
  auto-spending. Outbound work lands in the Out box and waits for him.
- Sending is OFF by default even where the plumbing exists.
- Credentials are set by him in .env, never handled in chat.
- Everything must keep working offline; cloud is an enhancement, never a
  dependency.
- The one sanctioned exception: Soro publishes blog posts to the site
  automatically. His choice, his tool -- do not pitch blog writing.
- Always do unasked: flag deadlines at risk, say when the numbers do not add
  up, and push back when he is wrong -- once, with the why, then let him
  decide.
[ASK BARRY: his top three priorities right now, in order, and his working
hours/rhythm.]

== STANDING CONTEXT ==
- Lifetime trade is small and honest: 51 orders / $2,869.82 completed since
  2024-03-13. Most "failures" in that history were a friend testing Klarna
  plus card-testing fraud, not lost customers.
- Email: Omnisend for bulk, Titan (info@bdubbgrowsllc.com) for 1:1.
- THE LIST IS NOT SAFE TO BULK-SEND YET -- contacts were manually subscribed,
  bot registrations need stripping, and bdubbgrowsllc.com is not authenticated
  in Omnisend. Never advise "email your list" until those are cleared.
- Ads: one Microsoft campaign, $10/day prepaid. Watch and report only until
  the data moves.
- Named competitor: Hydrobuilder -- they own paid search. His lanes are
  Bionova brand terms, owned email, and free Shopping listings.
- Stated goal: a brick-and-mortar store. The faster lever his cost basis
  unlocks is B2B -- selling Bionova to other shops at wholesale, still ~40%.

== NUMBERS HE STEERS BY ==
[ASK BARRY -- genuinely missing from this office and it blocks real analysis:
margin by line, AOV, repeat rate, traffic + conversion, list size + open rate,
ad spend/ROAS, inventory. Name the specific number you are missing and why it
changes the answer; never invent one.]
"""


def main():
    with memory.get_db() as conn:
        row = conn.execute(
            "SELECT id FROM facts WHERE source_name=? AND category=? "
            "AND status='active'", (SOURCE, CATEGORY)).fetchone()
        if row:
            conn.execute("UPDATE facts SET content=? WHERE id=?",
                         (CONTENT, row[0]))
            print(f"updated business-brain (fact {row[0]})")
            fid = row[0]
        else:
            fid = None
    if fid is None:
        memory.add_fact(category=CATEGORY, content=CONTENT,
                        source_name=SOURCE, title="business-brain")
        with memory.get_db() as conn:
            fid = conn.execute(
                "SELECT id FROM facts WHERE source_name=? AND category=? "
                "AND status='active'", (SOURCE, CATEGORY)).fetchone()[0]
        print(f"created business-brain (fact {fid})")

    # verify: present, ALWAYS-ON (no .md), and actually in her context block
    with memory.get_db() as conn:
        r = conn.execute("SELECT source_name, content FROM facts WHERE id=?",
                         (fid,)).fetchone()
    assert not r["source_name"].endswith(".md"), \
        "must be always-on -- the zip intends it to govern every reply"
    block = memory.brain_context_block("Operations")
    assert "BUSINESS BRAIN -- BARRY'S MASTER CONTEXT" in block, \
        "not riding in Priya's always-on context"
    gaps = r["content"].count("[ASK BARRY")
    print(f"VERIFIED: always-on, {len(CONTENT)} chars, in her context block "
          f"(now {len(block):,} chars). {gaps} honest gaps marked for Barry.")


if __name__ == "__main__":
    main()
