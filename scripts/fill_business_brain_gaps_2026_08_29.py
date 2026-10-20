"""Fill three [ASK BARRY] gaps in the Business Brain with Barry's OWN words.

2026-08-29: asked whether Priya distributes what she learns, the test message
gave her his dream client, his bad fit, and how he talks about Bionova. She
made ZERO tool calls -- did not save it, did not delegate it. His answers were
about to be lost, so they are recorded here verbatim.

VERBATIM. His wording, not a summary -- same rule as his canon.
Re-runnable: replaces the three placeholder blocks by exact match and asserts
each replacement landed.
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
import memory  # noqa: E402

SOURCE = "business-brain"

REPLACEMENTS = [
    (
        "== DREAM CLIENT / BAD FIT ==\n"
        "[ASK BARRY -- not recorded anywhere. Lead triage needs one sentence "
        "each.]",

        "== DREAM CLIENT / BAD FIT (Barry's own words, 2026-08-29) ==\n"
        "DREAM: \"a serious home grower running 4-12 lights who reorders "
        "nutrients every 6 weeks and actually reads labels.\"\n"
        "BAD FIT: \"the one-plant hobbyist hunting the cheapest bottle.\"\n"
        "Read what that implies before scoring a lead: the dream client is "
        "defined by REORDER RHYTHM and attention, not by order size -- a "
        "6-week nutrient cycle is the recurring revenue this business runs "
        "on. Price-shoppers are not a smaller version of that customer; they "
        "are a different one.",
    ),
    (
        "Grower-to-grower. Two modes: technical when the reader is technical,\n"
        "approachable when they are not. No corporate register.",

        "Grower-to-grower. Two modes: technical when the reader is technical,\n"
        "approachable when they are not. No corporate register.\n"
        "HOW HE TALKS ABOUT BIONOVA, his words 2026-08-29: \"grower-to-"
        "grower, never salesy -- I say what it did in my own tent and let the "
        "numbers do the talking.\" Two rules fall out of that and both are "
        "load-bearing: the proof is FIRST-HAND and it is HIS, so never write "
        "a tent story he did not tell you (use [PERSONAL BEAT: ...] and ask); "
        "and the numbers carry the claim, so cite the real ones from the "
        "Bionova evidence stack rather than adding adjectives.",
    ),
    # 2026-08-29, Barry, after Victor proposed looking up investors and
    # writing to them: "i dont want him contacting anybody. Besides he said
    # nothing about the non disclosure letter first."
    # TWO separate failures in one proposal, and the second is the expensive
    # one -- pitching PID to an outsider without an NDA can put its
    # confidential material in the open before anyone signs anything.
    (
        "- NOTHING acts without his approval. No auto-publishing, "
        "auto-sending or\n  auto-spending. Outbound work lands in the Out box "
        "and waits for him.",

        "- NOTHING acts without his approval. No auto-publishing, "
        "auto-sending or\n  auto-spending. Outbound work lands in the Out box "
        "and waits for him.\n"
        "- YOU DO NOT CONTACT ANYBODY. Not investors, not partners, not "
        "vendors,\n"
        "  not press, not customers -- not even to \"introduce\" or \"feel out\" "
        "or\n"
        "  \"gauge interest\". No looking up who to approach and no drafting "
        "outreach\n"
        "  unless Barry asks for it by name. He said this after a proposal to "
        "find\n"
        "  investors and write to them: \"i dont want him contacting "
        "anybody.\"\n"
        "  Relationships are his to open, always.\n"
        "- ANY INVESTOR OR PARTNER CONVERSATION STARTS WITH AN NDA. If you are "
        "ever\n"
        "  asked to help with outreach to an investor, an ODM, or a potential\n"
        "  partner -- especially anything touching PID -- the FIRST thing you "
        "raise\n"
        "  is the non-disclosure agreement, before a single word of the pitch. "
        "Loop\n"
        "  Marcus in. Barry had to point this out himself because it went "
        "unsaid;\n"
        "  never make him be the one who remembers it. Proposing outreach "
        "without\n"
        "  naming the NDA is a mistake, not an oversight.",
    ),
]


def main():
    with memory.get_db() as conn:
        row = conn.execute(
            "SELECT id, content FROM facts WHERE source_name=? "
            "AND status='active'", (SOURCE,)).fetchone()
        assert row, "business-brain fact not found"
        content = row["content"]
        before = content
        for old, new in REPLACEMENTS:
            assert content.count(old) == 1, \
                f"anchor not found exactly once:\n{old[:80]}"
            content = content.replace(old, new, 1)
        assert content != before
        conn.execute("UPDATE facts SET content=? WHERE id=?",
                     (content, row["id"]))

    with memory.get_db() as conn:
        after = conn.execute("SELECT content FROM facts WHERE source_name=? "
                             "AND status='active'", (SOURCE,)).fetchone()[0]
    for phrase in ["4-12 lights", "cheapest bottle", "let the numbers do the talking"]:
        assert phrase in after, f"verify failed: {phrase!r} not stored"
    gaps = after.count("[ASK BARRY")
    print(f"business-brain updated: {len(before)} -> {len(after)} chars")
    print(f"gaps remaining for Barry: {gaps} "
          "(top-3 priorities, working hours, Gotcho Back voice, steering numbers)")
    print("VERIFIED: his exact wording stored for dream client, bad fit, and "
          "the Bionova voice rule.")


if __name__ == "__main__":
    main()
