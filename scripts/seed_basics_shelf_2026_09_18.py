"""The basic-skills floor every new agent stands on -- `domain:basics`.

Barry, 2026-09-18: "math, files creations and reading etc are all part of basic
skills they can get. search tools and the like are basic tools they can get and
whatever other basic skills and tolls along with their new persona skills."
Then, sharpening it: "a new agent should be a blank slate until we add what that
new agent needs. we need to lock my personal stuff away."

A blank slate walled off from the shared tier has an EMPTY shelf at birth, which
is correct for privacy and useless as a colleague. This is the shelf that makes
it competent without telling it anything about him: checking numbers, reading and
writing files, looking things up, thinking it through.

⚠️ THE ONE RULE FOR THIS FOLDER: no venture, no store, no catalog, no customer,
no figure of his, no character of his. `domain:basics` is the shelf that reaches
an agent he builds FOR SOMEBODY ELSE, so this seeder REFUSES to seed a doc that
mentions his business. That guard is the point of the script, not decoration.

Granted automatically at hire (main._register_hire). Also grantable to the nine
if he ever wants it there -- deliberately NOT done: they already carry deeper
per-seat versions of all four, and duplicating craft is how two copies drift.
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "backend"))

import memory    # noqa: E402
import recall    # noqa: E402

FOLDER = os.path.join(REPO, "knowledge", "basics")
CATEGORY = "domain:basics"
MAX_CHARS = 18_500          # recall injects whole docs or names them

# His things. If any of these appear, the doc does not belong on this shelf.
FORBIDDEN = re.compile(
    r"\b(b ?dubb|bdubb|gotcho|piddevice|bionova|silution|global garden|"
    r"hydrobuilder|omnisend|simprosys|woocommerce|yieldcraft|"
    r"talia|vor'?shara|yannah|tazz|keth|bia\b)", re.I)

# The tool names genuinely carry his first name (send_file_to_barry,
# read_barrys_file), so a bare "barry" cannot be forbidden outright -- it is
# allowed ONLY inside a tool name or as the person being addressed.
_BARRY_OK = re.compile(r"(send_file_to_barry|read_barrys_file)", re.I)

DOCS = [
    ("checking-numbers.md", "checking-numbers"),
    ("reading-and-writing-files.md", "reading-and-writing-files"),
    ("looking-things-up.md", "looking-things-up"),
    ("thinking-it-through.md", "thinking-it-through"),
    # HIGH-LEVEL BASICS (Barry, 2026-09-18: "oh and they get high level basic
    # knowledge"). The four above are method; these two were the real gaps --
    # nothing on this shelf covered writing prose or making something
    # understood, which is most of what any agent actually hands over.
    ("writing-clearly.md", "writing-clearly"),
    ("explaining-things.md", "explaining-things"),
]

# Both directions. A basics doc must fire on plain work vocabulary and must NOT
# fire on ordinary conversation.
FIRE = [
    ("can you check my math on this total", "checking-numbers"),
    ("work out the percentage for me", "checking-numbers"),
    ("write it up in a file for me", "reading-and-writing-files"),
    ("read the document i put in your out box", "reading-and-writing-files"),
    ("look up what the current version is", "looking-things-up"),
    ("search for the latest guidance on this", "looking-things-up"),
    ("think it through before you answer", "thinking-it-through"),
    ("which of these two options is better", "thinking-it-through"),
    ("tighten this paragraph for me", "writing-clearly"),
    ("rewrite it in plain english", "writing-clearly"),
    ("explain how that works", "explaining-things"),
    ("i dont understand this part, break it down", "explaining-things"),
]
QUIET = ["morning", "thanks", "lol", "how are you doing today"]

# ⚠️ KNOWN FLOOR, not a failure -- printed so nobody re-discovers it as a bug.
# `recall.MIN_SCORE` is 10 and a routed word scores 3, so a message carrying one
# or two scorable words cannot clear the bar however good the routing line is.
# "whats 18% of 250" tokenises to nothing at all (the digits are not in any
# routing line and % is stripped); "can you research this for me" scores 3 on
# the single word "research". Both are handled fine WITHOUT the document -- one
# is arithmetic the model just does, the other is a search it just runs -- and
# `read_skill` remains the manual door. Lowering the floor is an office-wide
# change affecting all nine seats and is NOT worth it for this.
KNOWN_FLOOR = ["whats 18% of 250", "can you research this for me"]


def main() -> int:
    if not os.path.isdir(FOLDER):
        print(f"missing folder: {FOLDER}")
        return 1

    staged = []
    for filename, title in DOCS:
        path = os.path.join(FOLDER, filename)
        if not os.path.isfile(path):
            print(f"MISSING {filename}")
            return 1
        with open(path, encoding="utf-8") as fh:
            text = fh.read().strip()

        # 1. Nothing of his on this shelf.
        scrubbed = _BARRY_OK.sub("", text)
        hits = sorted({m.group(0).lower() for m in FORBIDDEN.finditer(scrubbed)})
        if hits:
            print(f"REFUSED {filename}: mentions {hits} -- basics is the shelf "
                  f"that reaches an agent built for somebody else")
            return 1

        # 2. Under the recall budget, or it gets named and never handed over.
        if len(text) > MAX_CHARS:
            print(f"REFUSED {filename}: {len(text):,} chars over {MAX_CHARS:,}")
            return 1

        # 3. One physical USE WHEN line, first line.
        first = text.splitlines()[0]
        if not first.startswith("USE WHEN:"):
            print(f"REFUSED {filename}: first line is not the routing line")
            return 1
        staged.append((filename, title, text, first))

    print(f"staged {len(staged)} docs, all clean of his business\n")

    for filename, title, text, _first in staged:
        with memory.get_db() as conn:
            conn.execute(
                "UPDATE facts SET status='superseded' WHERE category=? AND "
                "source_name=? AND status='active'", (CATEGORY, filename))
        memory.add_fact(CATEGORY, text, source_name=filename, title=title)
        print(f"  seeded {title:30} {len(text):>6,} chars")

    # VERIFY THE ROUTING LINE SURVIVED WHOLE. _skill_use_when reads the first
    # physical USE WHEN line inside content[:1200], and add_fact prepends a
    # TITLE line -- a long line silently loses its tail.
    print("\nrouting lines:")
    ok = True
    with memory.get_db() as conn:
        for filename, title, text, first in staged:
            row = conn.execute(
                "SELECT content FROM facts WHERE category=? AND source_name=? "
                "AND status='active' ORDER BY id DESC LIMIT 1",
                (CATEGORY, filename)).fetchone()
            got = (memory._skill_use_when({"content": row[0],
                                           "source_name": filename}, 1200) or "").strip()
            want = first.replace("USE WHEN:", "").strip()
            whole = got.endswith(want[-40:])
            ok = ok and whole
            print(f"  {title:30} {len(got):>4}c  {'WHOLE' if whole else 'TRUNCATED'}")

    # BEHAVIOUR, on a probe office granted exactly this domain -- which also
    # proves a hire with no other grant can reach them.
    probe = "__basics_probe"
    memory.grant_domain_access(probe, "basics")
    print("\nrouting battery (probe office, basics only):")
    fails = 0
    for msg, want in FIRE:
        _, titles = recall.recall_for_message(probe, msg)
        hit = want in titles
        fails += 0 if hit else 1
        print(f"  {'PASS' if hit else 'MISS':<5} {msg[:38]:<40} {titles[:2]}")
    for msg in QUIET:
        _, titles = recall.recall_for_message(probe, msg)
        quiet = not titles
        fails += 0 if quiet else 1
        print(f"  {'PASS' if quiet else 'FIRED':<5} quiet: {msg[:31]:<33} {titles}")

    print("\nknown floor (documented, not failures):")
    for msg in KNOWN_FLOOR:
        _, titles = recall.recall_for_message(probe, msg)
        print(f"  {'still under' if not titles else 'now routes':<11} {msg[:34]:<36} {titles}")

    # And the wall itself: the probe must see NOTHING of his.
    facts = memory.get_active_facts_for_agent(probe)
    leaked = [f["category"] for f in facts if not f["category"].startswith("domain:basics")]
    print(f"\nwall: probe sees {len(facts)} facts, "
          f"{len(leaked)} outside domain:basics {sorted(set(leaked))}")
    fails += 1 if leaked else 0

    with memory.get_db() as conn:
        conn.execute("DELETE FROM agent_domains WHERE office_name=?", (probe,))

    print()
    if ok and not fails:
        print("ALL CLEAR -- basics shelf seeded, routing, and nothing of his on it")
        return 0
    print(f"⚠️ {fails} problem(s){'' if ok else ' + a routing-line problem'}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
