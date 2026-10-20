"""CATEGORIZE THE PLANT SHELF FOR EASY ACCESS (Barry, 2026-09-18: "yes make
sure its all categorized, for easy access").

In this office "categorized" is the USE WHEN routing line, because that is what
recall actually reads -- a doc without one is reachable only through read_skill,
which fires in about 1% of calls. The audit found two real problems:

1. TWO DOCS HAD NO ROUTING LINE AT ALL and were effectively invisible:
   bionova-and-recommendations (the why-Bionova story and the recommendation
   playbook) and indoor-crops-and-equipment (crop-to-gear matching). Both are
   good content that nobody could reach.

2. THREE DOCS NOW COLLIDE on the same plant names. The new per-plant lookup,
   the older houseplants prose and tropical-plants all listed monstera, pothos,
   philodendron, ficus, orchid, palm, calathea. Recall injects WHOLE docs
   against a 20K budget, so two 10K plant docs firing together eat the whole
   budget and squeeze out the product map -- which is the "how what we sell
   could help" half. This is the prop-shot-structure collision from 2026-08-16
   repeating: a doc carrying another doc's vocabulary steals its jobs.

THE FIX IS TO SPLIT BY JOB, NOT BY TOPIC. Each doc keeps the words for the
question it is the best answer to, and gives up the words that belong to
another:

  * the per-plant lookup owns "what does this plant NEED" -- plant names plus
    medium/light/feeding/pH;
  * houseplants prose owns CARE AND PESTS -- repotting, fungus gnats, mites,
    dust, acclimation, humidity;
  * tropical-plants owns what is genuinely tropical-only -- bromeliad, hoya,
    dracaena, pet-safe, retail;
  * diagnosing-plant-problems keeps the symptom words it already owned.

Nothing is deleted and no body text is touched -- only the routing lines move.
Backup of every original line is written before anything changes.
"""
import json
import os
import sys
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "backend"))

import memory   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# source_name -> the routing line it should carry (without the "USE WHEN: ")
LINES = {
    # --- was unreachable: no routing line at all ---
    "bionova-and-recommendations.md":
        "why bionova, about bionova, bionova line, recommend bionova, the "
        "bionova system, why this brand, what makes it different, "
        "recommendation playbook, how to recommend, talking to a customer "
        "about nutrients, which brand should i buy.",
    "indoor-crops-and-equipment.md":
        "what gear, what equipment, grow tent, tents, grow light, grow lights, "
        "led, fan, ventilation, filter, what do i need to start, setting up a "
        "grow, kit, equipment for herbs, equipment for houseplants, what "
        "customers grow indoors.",

    # --- de-collided: gave up the plant names to the per-plant lookup ---
    "houseplants.md":
        "houseplant care, indoor plant care, repot, repotting, potting on, "
        "fungus gnats, spider mites, mealybug, scale, pests on a houseplant, "
        "dusty leaves, leaf cleaning, acclimating a new plant, humidity for "
        "houseplants, winter care, holiday watering.",
    "tropical-plants.md":
        "tropical, tropicals, bromeliad, hoya, dracaena, anthurium, "
        "aglaonema, pet safe, pet-safe, toxic to cats, toxic to dogs, "
        "humidity, misting, terrarium, tropical retail, selling tropicals.",

    # --- same collision on the edibles side: three docs all claimed basil ---
    "herbs-and-microgreens.md":
        "growing herbs, harvesting herbs, pinching, pruning herbs, succession "
        "sowing, drying herbs, preserving, seed density, blackout period, "
        "microgreen tray, growing microgreens, harvesting microgreens, herb "
        "garden setup, bolting.",
    "vegetables-and-fruit.md":
        "growing vegetables, pollination, hand pollinating, trellis, "
        "training, pruning tomatoes, suckering, container size, variety "
        "choice, succession planting, harvest timing, fruit set, crop "
        "rotation, growing fruit indoors.",
}

CHECK_UNIQUE = {           # words that must now belong to exactly one doc
    "monstera": "houseplants-houseplant-monstera-aloe-pothos-ficus-orchid.md",
    "basil": "herbs-veg-basil-mint-tomato-lettuce-indoors-edible.md",
}


def _use_when_line(content: str) -> str | None:
    for line in content.splitlines():
        if line.strip().upper().startswith("USE WHEN:"):
            return line
    return None


def main() -> None:
    facts = {f["source_name"]: f for f in
             memory.get_active_facts_for_agent("Marketing")}
    stamp = datetime.datetime.now().strftime("%Y-%m-%d")
    backup, changed = {}, 0

    for source, new_line in LINES.items():
        fact = facts.get(source)
        if not fact:
            print(f"  ?? {source} not on the shelf -- skipped")
            continue
        content = fact["content"]
        old = _use_when_line(content)
        backup[source] = {"id": fact["id"], "old_use_when": old}

        want = f"USE WHEN: {new_line}"
        if old:
            body = content.replace(old, want, 1)
        else:
            # no routing line -- insert one directly above the first heading so
            # it lands inside the 1200-char window _skill_use_when scans
            lines = content.splitlines()
            at = next((i for i, l in enumerate(lines)
                       if l.lstrip().startswith("#")), 0)
            lines.insert(at, want)
            lines.insert(at + 1, "")
            body = "\n".join(lines)

        with memory.get_db() as conn:
            conn.execute("UPDATE facts SET content = ? WHERE id = ?",
                         (body, fact["id"]))
        changed += 1

    path = os.path.join(ROOT, "data", f"backup_routing_lines_{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(backup, f, indent=1)

    # --- verify every one reads back in full ---
    print(f"rewrote {changed} routing lines; backup {os.path.basename(path)}\n")
    facts = {f["source_name"]: f for f in
             memory.get_active_facts_for_agent("Marketing")}
    for source, new_line in LINES.items():
        if source not in facts:
            continue
        read = memory._skill_use_when(facts[source], 1200) or ""
        ok = read.rstrip(".").startswith(new_line.rstrip(".")[:100])
        print(f"  {'OK  ' if ok else 'FAIL'} {source[:46]:48} {read[:52]}")
        assert ok, f"{source}: routing line did not read back"

    # --- the collision words now belong to exactly one doc ---
    print()
    for word, owner in CHECK_UNIQUE.items():
        holders = [sn for sn, f in facts.items()
                   if (f.get("category") or "").startswith(("domain:horticulture",
                                                            "knowledge:bdubb"))
                   and word in (memory._skill_use_when(f, 1200) or "").lower()]
        print(f"  '{word}' routes from: {holders}")
        assert holders == [owner], f"'{word}' still collides: {holders}"

    # --- nothing left unroutable on either shelf ---
    print()
    orphans = [sn for sn, f in facts.items()
               if (f.get("category") or "") in ("domain:horticulture",
                                                "knowledge:bdubb_products")
               and not memory._skill_use_when(f, 1200)]
    print("unroutable docs remaining:", orphans or "none")
    assert not orphans


if __name__ == "__main__":
    main()
