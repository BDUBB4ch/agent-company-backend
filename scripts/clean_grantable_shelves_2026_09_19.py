"""Scrub his world off the shelves a NEW AGENT can be given (2026-09-19).

Barry: "what needs to be done is making sure the basic and special and tools we
give is devoid of me and my personal stuff. there should be no way that b dubb
grows, gotcho back or barry should show up. Bia none of that stuff either."

Measured before touching anything -- six documents on grantable shelves named
his world:

  domain:horticulture  bionova-and-recommendations.md   bionova x9, barry x1
  domain:herbs         medicinal-herbs-and-plants.md    b dubb, colorado springs x2
  domain:herbs         herbs-...-indoors-what-they-need b dubb
  domain:houseplants   tropical-plants.md               colorado springs
  domain:houseplants   houseplants-...-ficus-orchid     b dubb
  domain:vegetables    vegetables-...-indoors-needs     b dubb

TWO DIFFERENT PROBLEMS, TWO DIFFERENT FIXES:

1. bionova-and-recommendations.md is not incidental -- it IS his product line,
   nine mentions deep. It does not get scrubbed, it gets RE-FILED to
   `business:bdubbgrows`, where the shared tier already puts it in front of his
   nine and the 2026-09-18 wall already keeps it away from everyone else. A
   product catalogue was never generic plant science; this is the filing being
   corrected, not content being lost.

2. The other five are passing references -- a disclaimer worded around his
   store, four cross-reference lines pointing at "the B Dubb product guide",
   and two location paragraphs naming his city. Every one of them says the
   same thing with the name taken out, so they are rewritten in place. The
   horticulture is untouched: zone 6a, 6,000 ft and semi-arid all stay, they
   just stop identifying where he lives.

Re-runnable: each edit is asserted and an already-clean doc is skipped.
Backup of every original: data/backup_grantable_shelves_2026-09-19.json
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PROJECT, "backend"))

import memory  # noqa: E402

BACKUP = os.path.join(PROJECT, "data", "backup_grantable_shelves_2026-09-19.json")

# The shelves a new agent can be handed. These must never name his world.
GENERIC = ["basics", "research", "authorship", "horticulture", "herbs",
           "houseplants", "vegetables", "fruit_trees"]

HIS_WORLD = re.compile(
    r"\b(barry|b\s*dubb\s*grows|b\s*dubb|bdubb|gotcho\s*back|gotcho|yieldcraft|"
    r"bionova|silution|piddevice|hydrobuilder|global\s+garden|omnisend|"
    r"simprosys|bdubbgrowsllc|talia|bia|vor'?shara|yannah|tazz|keth|"
    r"colorado\s+springs)\b", re.I)

# 1. RE-FILE -- his product guidance, wrongly sitting on a generic plant shelf.
REFILE = [("domain:horticulture", "bionova-and-recommendations.md",
           "business:bdubbgrows")]

# 2. REWRITE -- passing references. (source_name, old, new)
REWRITES = [
    # the medical disclaimer, worded around his store
    ("medicinal-herbs-and-plants.md",
     "B Dubb Grows sells growing supplies and cultivation know-how. It does not "
     "sell medicine and its agents are not medical professionals.",
     "This is a growing-supplies and cultivation resource. It does not deal in "
     "medicine and you are not a medical professional."),
    # the location sections -- the growing facts stay, the address goes
    ("medicinal-herbs-and-plants.md",
     "## Colorado Springs growing context",
     "## High-desert growing context"),
    ("medicinal-herbs-and-plants.md",
     "Colorado Springs sits mostly in **USDA zone 6a**",
     "A high-desert location around 6,000 ft sits mostly in **USDA zone 6a**"),
    ("tropical-plants.md",
     "Colorado Springs sits at ~6,000 ft, semi-arid.",
     "A high-desert location at ~6,000 ft is semi-arid."),
    # four cross-reference lines pointing at his catalogue
    ("herbs-basil-mint-rosemary-thyme-indoors-what-they-need.md",
     "which product answers it is in the B Dubb product",
     "which product answers it is in the product"),
    ("houseplants-houseplant-monstera-aloe-pothos-ficus-orchid.md",
     "which product answers it is in the B Dubb product",
     "which product answers it is in the product"),
    ("vegetables-veg-tomato-lettuce-pepper-indoors-needs.md",
     "which product answers it is in the B Dubb product",
     "which product answers it is in the product"),
]


def rows_for(domain):
    with memory.get_db() as conn:
        return conn.execute(
            "SELECT id, source_name, content FROM facts "
            "WHERE category = ? AND status = 'active'", ("domain:" + domain,)).fetchall()


def main() -> int:
    # ---- back up every grantable doc before a single write -----------------
    snapshot = []
    for d in GENERIC:
        for r in rows_for(d):
            snapshot.append({"id": r["id"], "domain": d,
                             "source_name": r["source_name"], "content": r["content"]})
    os.makedirs(os.path.dirname(BACKUP), exist_ok=True)
    with open(BACKUP, "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, indent=1)
    print("backed up %d documents -> %s\n" % (len(snapshot), os.path.basename(BACKUP)))

    # ---- 1. re-file his product guidance ------------------------------------
    for cat, source, new_cat in REFILE:
        with memory.get_db() as conn:
            n = conn.execute(
                "UPDATE facts SET category = ? WHERE category = ? AND source_name = ? "
                "AND status = 'active'", (new_cat, cat, source)).rowcount
        print("re-filed  %-34s %s -> %s%s"
              % (source, cat, new_cat, "" if n else "   (already moved)"))

    # ---- 2. rewrite the passing references ----------------------------------
    print()
    for source, old, new in REWRITES:
        with memory.get_db() as conn:
            row = conn.execute(
                "SELECT id, content FROM facts WHERE source_name = ? AND status = 'active' "
                "AND category LIKE 'domain:%'", (source,)).fetchone()
        if not row:
            print("  MISSING  %s -- skipped" % source)
            continue
        body = row["content"]
        if old not in body:
            print("  ok       %-46s (already clean)" % source[:46])
            continue
        body = body.replace(old, new)
        assert new in body and old not in body, source
        with memory.get_db() as conn:
            conn.execute("UPDATE facts SET content = ? WHERE id = ?", (body, row["id"]))
        print("  rewrote  %-46s %s" % (source[:46], old[:34] + "…"))

    # ---- 3. VERIFY FROM THE DATABASE, every grantable shelf -----------------
    print("\nEvery shelf a new agent can be given:")
    dirty = 0
    for d in GENERIC:
        bad = []
        for r in rows_for(d):
            hits = sorted({m.group(0).lower() for m in HIS_WORLD.finditer(r["content"] or "")})
            if hits:
                bad.append((r["source_name"], hits))
        if bad:
            dirty += len(bad)
            print("  %-14s DIRTY" % d)
            for s, h in bad:
                print("      %-46s %s" % (s[:46], ", ".join(h)))
        else:
            print("  %-14s clean" % d)

    print()
    if dirty:
        print("%d document(s) still name his world." % dirty)
        return 1
    print("CLEAN -- nothing a new agent can be given names him, his businesses "
          "or his characters.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
