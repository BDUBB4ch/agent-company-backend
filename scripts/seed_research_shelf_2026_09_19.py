"""The RESEARCH shelf -- domain:research (2026-09-19).

Barry: "all my creations need to be as smart as possible for what they are used
for. this new agent will be for research too. so she will definitely need that
skill."

Three documents, one concern each:
    running-a-real-investigation  many searches, sub-questions, when to stop
    judging-a-source              primary vs downstream, evidence, conflicts
    reporting-what-you-found      established / likely / open, honest gaps

WHY ITS OWN SHELF and not more `basics` documents: every agent is born with the
basics floor (6 docs, already on every seat), and `looking-things-up` covers
query craft. Only some agents are doing research. Granting it is one call, and
main.suggest_kit matches it from a title that mentions research.

GRANTED TO NOBODY BY THIS SCRIPT -- like the authorship shelf. A shelf that
exists and reaches no one is exactly what a kit built before its agent should
be (2026-09-18).

⚠️ THE GUARD IS THE POINT: this shelf can reach an agent he builds for somebody
else, so a document naming any venture, product, character or figure of his is
REFUSED, not warned about. Same rule as the basics seeder.

Re-runnable: supersedes by source_name, never duplicates.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PROJECT, "backend"))

import memory  # noqa: E402

DOCS_DIR = os.path.join(PROJECT, "knowledge", "research")
DOMAIN = "research"
CATEGORY = f"domain:{DOMAIN}"
RECALL_CEILING = 18_500          # recall injects whole docs or names them

# His world. Anything here means the document does not belong on a shelf that
# can be handed to somebody else's agent.
FORBIDDEN = re.compile(
    r"\b(b\s*dubb|bdubb|gotcho|yieldcraft|bionova|silution|piddevice|"
    r"\bpid\b|global garden|hydrobuilder|omnisend|woocommerce|simprosys|"
    r"talia|bia\b|vor'?shara|yannah|tazz|keth|elliot|amara|priya|victor|"
    r"marcus|derek|vivian|sophie|taliyah|barry)\b", re.I)


def check(name: str, body: str) -> list:
    problems = []
    if len(body) > RECALL_CEILING:
        problems.append("%d chars -- over the %d recall ceiling, it would be "
                        "named and never handed over" % (len(body), RECALL_CEILING))
    first = body.splitlines()[0] if body.splitlines() else ""
    if not first.startswith("USE WHEN:"):
        problems.append("no USE WHEN line on the first physical line")
    elif len(first) > 1150:
        problems.append("USE WHEN line is %d chars -- the tail is past the "
                        "1200-char read window" % len(first))
    hits = sorted({m.group(0).lower() for m in FORBIDDEN.finditer(body)})
    if hits:
        problems.append("names his world: %s" % ", ".join(hits))
    return problems


def main() -> int:
    if DOMAIN not in memory.KNOWN_DOMAINS:
        print("FAIL: '%s' is not in memory.KNOWN_DOMAINS -- add it first." % DOMAIN)
        return 1
    files = sorted(f for f in os.listdir(DOCS_DIR) if f.endswith(".md"))
    if not files:
        print("FAIL: no documents in %s" % DOCS_DIR)
        return 1

    staged, refused = [], []
    for fn in files:
        with open(os.path.join(DOCS_DIR, fn), encoding="utf-8") as fh:
            body = fh.read().strip()
        problems = check(fn, body)
        if problems:
            refused.append((fn, problems))
        else:
            staged.append((fn, body))

    for fn, problems in refused:
        print("REFUSED %s" % fn)
        for p in problems:
            print("        - %s" % p)
    if refused:
        print("\nNothing seeded. Fix those first -- the guard is the point of "
              "this script.")
        return 1

    print("Seeding %d documents to %s\n" % (len(staged), CATEGORY))
    for fn, body in staged:
        source = fn                       # keep the .md -- on-demand, not always-on
        # ⚠️ add_fact does NOT supersede by source_name -- it inserts. The first
        # re-run of this script filed a second copy of all three docs, which is
        # two rows recall can both match. Retire the old row first; never
        # delete (the house rule), just mark it superseded.
        with memory.get_db() as conn:
            n = conn.execute(
                "UPDATE facts SET status = 'superseded' "
                "WHERE category = ? AND source_name = ? AND status = 'active'",
                (CATEGORY, source)).rowcount
        memory.add_fact(CATEGORY, body, source_name=source,
                        title=fn[:-3].replace("-", " "))
        print("  + %-34s %6d chars%s"
              % (source, len(body), "  (replaced %d)" % n if n else ""))

    # VERIFY FROM THE DATABASE, not from what we just wrote (2026-09-18: a
    # checker that probes an agent's shelf returns nothing for a domain granted
    # to nobody, so it silently cannot fail).
    print("\nVerifying what is actually stored:")
    ok = True
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT source_name, content FROM facts "
            "WHERE category = ? AND status = 'active' ORDER BY source_name",
            (CATEGORY,)).fetchall()
    on_disk = {fn for fn, _ in staged}
    for r in rows:
        name, body = r["source_name"], r["content"] or ""
        line = memory._skill_use_when({"content": body}, 1200) or ""
        want = ""
        if name in on_disk:
            with open(os.path.join(DOCS_DIR, name), encoding="utf-8") as fh:
                want = fh.readline().strip()
        # ⚠️ _skill_use_when returns the line WITHOUT its "USE WHEN:" prefix.
        # Comparing against the raw file line reports every healthy doc as
        # truncated -- which is what the first run of this script did.
        want_words = want[len("USE WHEN:"):].strip() if want.startswith("USE WHEN:") else want
        whole = bool(want_words) and line.strip() == want_words
        print("  %-34s %6d chars  routing line %s"
              % (name, len(body), "WHOLE" if whole else "TRUNCATED/MISSING"))
        if not whole:
            ok = False

    audience = memory.get_domain_offices(DOMAIN) if hasattr(
        memory, "get_domain_offices") else None
    if audience is None:
        with memory.get_db() as conn:
            audience = [r[0] for r in conn.execute(
                "SELECT office_name FROM agent_domains WHERE domain = ?",
                (DOMAIN,)).fetchall()]
    print("\nGranted to: %s" % (", ".join(audience) if audience
                                else "nobody (correct -- it waits for its agent)"))
    print("\n%s" % ("ALL GOOD." if ok else "PROBLEM: a routing line did not survive."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
