"""Product knowledge becomes something he GIVES, not something inherited.

Barry, 2026-09-19: "she should know about the Bionova products, she needs to
know what they're made of and all to assist the team" -- then, in the same
breath about a different agent: "i dont want My author when i create it to know
anything."

Both at once is only possible if the product knowledge is a SHELF he can hand
over, rather than a shared-tier category that either everybody sees or nobody
does. Today it is the latter, which is why it could not be given to her without
also being sitting there for anyone else.

THE SPLIT, and it is the point of this script:

  WHAT THE PRODUCTS ARE        -> domain:bdubb_products   (grantable)
      what is in them, what they do, which one answers which problem, the
      feeding chart, the lab results. This is horticulture with his brand on
      it, and it is what a specialist needs to advise his team.

  WHAT THEY COST HIM           -> business:bdubbgrows     (stays, shared tier)
      cost basis, wholesale pricelists, suggested retail, margins, the
      competitor read, the business brain. His money. A horticulture
      specialist does not need it to answer a plant question, and the wall
      built on 2026-09-18 keeps it with his nine.

Nothing is lost for the nine: the new domain is granted to all nine offices, so
every seat that could see these documents this morning still can.

Re-runnable and reversible: the moves are recorded in
data/backup_products_domain_2026-09-19.json with the category each doc came
from.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PROJECT, "backend"))

import memory  # noqa: E402

BACKUP = os.path.join(PROJECT, "data", "backup_products_domain_2026-09-19.json")
DOMAIN = "bdubb_products"
CATEGORY = "domain:" + DOMAIN

# What the products ARE. Deliberately NOT the cost/pricelist/margin documents.
PRODUCT_KNOWLEDGE = [
    "bionova-line-selling-guide.md",
    "which-product-for-which-job-bionova-deficiency-fix.md",
    "bionova-and-recommendations.md",
    "bionova-coco-feeding-chart.md",
    "bionova-innexo-lab-results.md",
]

# Every office that can see these today, so nobody loses anything.
ALL_NINE = ["CIO", "Operations", "BusinessOps", "Legal", "Marketing",
            "Creative", "MovieDirector", "Engineer", "Taliyah"]


def main() -> int:
    if DOMAIN not in memory.KNOWN_DOMAINS:
        print("FAIL: add '%s' to memory.KNOWN_DOMAINS first." % DOMAIN)
        return 1

    moved, missing = [], []
    with memory.get_db() as conn:
        for source in PRODUCT_KNOWLEDGE:
            row = conn.execute(
                "SELECT id, category FROM facts WHERE source_name = ? "
                "AND status = 'active'", (source,)).fetchone()
            if not row:
                missing.append(source)
                continue
            if row["category"] == CATEGORY:
                print("  already there   %s" % source)
                continue
            moved.append({"source_name": source, "from": row["category"],
                          "to": CATEGORY, "id": row["id"]})
            conn.execute("UPDATE facts SET category = ? WHERE id = ?",
                         (CATEGORY, row["id"]))
            print("  moved           %-54s %s -> %s"
                  % (source[:54], row["category"], CATEGORY))

    for s in missing:
        print("  NOT FOUND       %s" % s)

    if moved:
        with open(BACKUP, "w", encoding="utf-8") as fh:
            json.dump(moved, fh, indent=1)
        print("\n  reversal recorded -> %s" % os.path.basename(BACKUP))

    print("\nGranting to the nine so nothing is lost:")
    for office in ALL_NINE:
        try:
            memory.grant_domain_access(office, DOMAIN)
            print("  + %s" % office)
        except Exception as exc:  # noqa: BLE001
            print("  ! %s: %s" % (office, exc))

    print("\nVerifying:")
    for office in ("BusinessOps", "Taliyah"):
        names = {f["source_name"] for f in memory.get_active_facts_for_agent(office)}
        have = [s for s in PRODUCT_KNOWLEDGE if s in names]
        print("  %-12s sees %d of %d product documents" % (office, len(have), len(PRODUCT_KNOWLEDGE)))

    with memory.get_db() as conn:
        left = conn.execute(
            "SELECT source_name FROM facts WHERE category = 'business:bdubbgrows' "
            "AND status = 'active' ORDER BY source_name").fetchall()
    print("\n  still his alone (cost, margins, the business brain): %d documents"
          % len(left))
    for r in left[:6]:
        print("      %s" % (r["source_name"] or "(always-on)"))
    print("      ...")
    print("\nA new agent gets these only if he ticks the shelf. Nothing inherits.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
