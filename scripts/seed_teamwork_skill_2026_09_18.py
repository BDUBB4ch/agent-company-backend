"""Teach the office how to actually use each other -- filed as ONE shared fact.

Barry, 2026-09-18: "block buzz is how all the agents could talk to each other,
i do have goup chat but they cant ask priya to do research for them."
Then, the same session: "everything needs to be categorized as well."

MEASURED before writing anything, because the tool already existed: every
business seat has carried `delegate_to` since 2026-09-02 and Priya has always
been a valid target. The briefs table says the capability is real but unused --
Victor->Priya 6 times, Vivian->Priya once, Marcus->Priya once, and Derek, who
needs research more than anyone, ZERO. So this is a habit and discoverability
gap, not missing plumbing, which is exactly what a routed skill fixes.

⚠️ CATEGORISATION -- the first pass of this script got it wrong and Barry
caught it. `ingest.teach` files into `private:<office>`, so teaching eight
seats wrote EIGHT copies of one 4.8K document: eight rows to keep in sync, and
a straight violation of the house filing rule (one fact, one home). It is now
ONE fact in a new shared category `knowledge:teamwork`, which every seat that
holds delegate_to can see. Taliyah was excluded from it for a day on the then-
correct reasoning that she lacked the tool; Barry changed that fact the same
session and she is now in.

ROUTING -- the first routing line was also wrong, and the battery caught it.
It carried TOPIC words (competitor, supplier, pricing, market) and therefore
competed against the domain docs that genuinely own those words, losing 4 of 6
cases to the price list and the tax doc. That was the right outcome for those
questions. This skill fires on the ACT of handing work over, not on the subject
matter, so the line is delegation vocabulary only.

Re-runnable: supersedes the private copies and any earlier shared version.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "backend"))

import memory    # noqa: E402
import recall    # noqa: E402

DOC = os.path.join(REPO, "knowledge", "working-with-your-teammates.md")
CATEGORY = "knowledge:teamwork"
SOURCE = "working-with-your-teammates.md"          # .md = on-demand, not always-on
TITLE = "working-with-your-teammates"

# Every seat holding delegate_to (main._SEAT_TOOLS). Taliyah was absent for one
# day and joined 2026-09-18 (Barry: "she also needs to be able to put together
# my ideas i come up with and file it and hand it to the team") -- she now holds
# the tool. Still NOT a business seat: the commercial categories remain excluded
# from her in memory._SHARED_CATEGORY_EXCLUSIONS. She hands HIS ideas over; she
# does not join the commercial stack.
SEATS = ["CIO", "Operations", "BusinessOps", "Legal", "Marketing",
         "Creative", "MovieDirector", "Engineer", "Taliyah"]

FIRE = [("Marketing", "who should i ask about this, its not really my lane"),
        ("Marketing", "can i hand this off to priya"),
        ("Creative", "i want to delegate the sourcing research"),
        ("BusinessOps", "get priya on it and put it on the board"),
        ("Legal", "whose job is the zoning research"),
        ("CIO", "file a brief for derek"),
        ("Taliyah", "put my idea together and hand it to the team"),
        ("Taliyah", "can you file this idea for the team")]
QUIET = [("Marketing", "write me a subject line for the saturday email"),
         ("Creative", "render the silution bottle on a white background"),
         ("BusinessOps", "whats our margin on mgo 10"),
         ("CIO", "say ok"),
         ("MovieDirector", "give me shot 3"),
         # These SHOULD go to the domain docs that own the topic, not here.
         ("Marketing", "what are competitors charging for grow tents"),
         ("Legal", "research commercial zoning rules")]


def main() -> int:
    with open(DOC, encoding="utf-8") as fh:
        text = fh.read().strip()
    print(f"doc: {len(text):,} chars")

    # Recall injects WHOLE documents against RECALL_BUDGET and never clips --
    # an over-budget doc gets NAMED and never handed over (the 2026-09-17
    # GG-pricelist failure). Stay well under.
    if len(text) > 18_500:
        print("REFUSING: over the recall budget, split it first")
        return 1

    # 1. Retire the eight private copies from the first pass, and any earlier
    #    shared version. Superseded, never deleted -- house rule.
    retired = 0
    with memory.get_db() as conn:
        for office in SEATS:
            cur = conn.execute(
                "UPDATE facts SET status='superseded' "
                "WHERE category=? AND source_name LIKE ? AND status='active'",
                (f"private:{office}", f"{TITLE}%"))
            retired += cur.rowcount
        cur = conn.execute(
            "UPDATE facts SET status='superseded' "
            "WHERE category=? AND status='active'", (CATEGORY,))
        retired += cur.rowcount
    print(f"retired {retired} earlier row(s) (superseded, not deleted)")

    # 2. One fact, one home.
    memory.add_fact(CATEGORY, text, source_name=SOURCE, title=TITLE)
    print(f"filed 1 fact in {CATEGORY}")

    # 3. Verify audience: the eight see exactly one copy, Taliyah sees none.
    print("\naudience check:")
    ok = True
    for office in SEATS:
        facts = memory.get_active_facts_for_agent(office)
        mine = [f for f in facts if (f.get("source_name") or "") == SOURCE]
        want = 1
        good = len(mine) == want
        ok = ok and good
        print(f"  {office:<14} sees {len(mine)} (want {want}) {'ok' if good else 'WRONG'}")

    # 4. Verify the routing line survived whole. _skill_use_when reads only the
    #    FIRST PHYSICAL LINE starting 'USE WHEN:' inside content[:1200], and
    #    add_fact prepends a TITLE line -- so a long heading can silently eat
    #    the tail. Assert the OUTCOME, never that the write "ran".
    want_line = next(l for l in text.splitlines() if l.startswith("USE WHEN:"))
    tail = want_line.replace("USE WHEN:", "").strip()[-40:]
    row = next(f for f in memory.get_active_facts_for_agent("Marketing")
               if (f.get("source_name") or "") == SOURCE)
    got = (memory._skill_use_when(row, 1200) or "").strip()
    whole = got.endswith(tail)
    print(f"\nrouting line: {len(got)} chars, {'WHOLE' if whole else 'TRUNCATED'}")
    ok = ok and whole

    # 5. Behaviour, both directions. Presence is not routing.
    print("\nrouting battery:")
    fails = 0
    for office, msg in FIRE:
        _, titles = recall.recall_for_message(office, msg)
        hit = TITLE in titles
        fails += 0 if hit else 1
        print(f"  {'PASS' if hit else 'MISS':<5} fire  | {msg[:44]:<46} {titles[:3]}")
    for office, msg in QUIET:
        _, titles = recall.recall_for_message(office, msg)
        quiet = TITLE not in titles
        fails += 0 if quiet else 1
        print(f"  {'PASS' if quiet else 'FIRED':<5} quiet | {msg[:44]:<46} {titles[:3]}")

    print()
    if ok and not fails:
        print("ALL CLEAR -- filed, scoped and routing correctly")
        return 0
    print(f"⚠️ {fails} routing problem(s){'' if ok else ', plus a filing/routing-line problem'}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
