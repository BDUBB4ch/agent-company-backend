"""Routing lines for Elliot's 32 unrouted on-demand docs -- Barry,
2026-08-25: "not rewrite just put associations near where he needs them
for quick access."

This is phase 2 of the memory-reflex plan (routing lines for the
undescribed docs), done for Elliot first. A USE WHEN first line is the
association: recall reads it on every message and serves the doc at the
moment it matters. One line PREPENDED, the content below it untouched --
the same operation as scripts/add_use_when_grammar_skills_2026_08_16.py.

DELIBERATELY SKIPPED, with reasons:
  barry-character-canon.md   fact 592 is byte-synced with the disk copy
                             (data/barry-character-canon.md); editing one
                             side is the documented drift trap, and the
                             pinned anchors-card covers character asks.
  ep1-production-v9-WIP.md   machine-managed by script_wip.py and served
  EP1_Production_V9.md       via read_scene / the verbatim gate; a
                             prepended line risks the structural parser.
  character-anchors-card.md  PINNED -- in the prompt in full; routing a
  flagging-judgment-calls.md pinned doc is documented waste.

Idempotent: a doc already starting with USE WHEN is left alone, so
re-running is safe. Full backup of every touched fact first.

Usage:  ../venv/Scripts/python.exe scripts/add_use_when_routing_2026_08_25.py
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import memory  # noqa: E402

BACKUP = os.path.join(os.path.dirname(__file__), "..", "data",
                      "backup_use_when_routing_2026-08-25.json")

# Written from the docs' actual heads (read before tagging), never guessed.
ROUTES = {
    "Talia_Crew_Series_Bible_July2026.md":
        "USE WHEN: Barry asks about character bios, backstories, "
        "relationships, or the story so far across the series.",
    "Shenna_Vel_Canon_Update.md":
        "USE WHEN: Shenna Vel comes up, or Season 2 future-canon "
        "characters are being discussed.",
    "character-consistency.md":
        "USE WHEN: keeping a character on-model across angles, shots or "
        "renders -- consistency techniques for this machine.",
    "talia-crew-brain-dump.md":
        "USE WHEN: deep lore digging -- details the bible and premise "
        "don't cover; the raw early notes on the Talia Crew.",
    "talia-crew-premise.md":
        "USE WHEN: Barry asks about the world, the setting, the premise, "
        "or how Earth relates to the wider universe.",
    "talia-crew-project-overview.md":
        "USE WHEN: asked what the Talia Crew project IS -- its type, "
        "status, or creative direction at a glance.",
    "bia-adventurer-storyboard.md":
        "USE WHEN: the old Bia adventurer / Puffclovers planet concept "
        "comes up -- ABANDONED concept, historical reference only.",
    "Approved idea.md":
        "USE WHEN: asked what Barry-approved priority is currently "
        "outstanding from the ideation queue.",
    "loc_colorado-black-site.png.md":
        "USE WHEN: writing or prompting the Colorado black-site exterior "
        "-- visual description of the fortified airbase location plate.",
    "Black site.png.md":
        "USE WHEN: writing or prompting the black-site airbase at night "
        "-- alternate visual description of the location plate.",
    "Screenshot (347).png.md":
        "USE WHEN: Barry refers to that desktop screenshot he shared "
        "(overlapping application windows).",
    "director-persona.md":
        "USE WHEN: asked how the director persona itself is defined -- "
        "the readable copy of Barry's own persona text.",
    "director-influences.md":
        "USE WHEN: asked about directing influences or style DNA -- Woo, "
        "Wick, Blade Runner, Mass Effect, Tony Jaa, Tarantino.",
    "product-catalog-full/SKILL.md":
        "USE WHEN: exact product names, prices or specs are needed and "
        "the lookup_product tool is unavailable -- the full B Dubb "
        "catalog dump.",
}


def history_line(source_name: str) -> str:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", source_name)
    when = m.group(1) if m else "an earlier date"
    return (f"USE WHEN: Barry asks what was discussed, decided or worked "
            f"on around {when}, or refers back to that conversation.")


def main() -> None:
    facts = memory.get_active_facts_for_agent("MovieDirector")
    touched, skipped, backup = [], [], []
    with memory.get_db() as conn:
        for f in facts:
            sn = f.get("source_name") or ""
            if not sn.endswith(".md"):
                continue
            content = f["content"]
            if content.lstrip().lower().startswith("use when:"):
                continue  # already routed
            if sn in ROUTES:
                line = ROUTES[sn]
            elif sn.startswith("conversation-history"):
                line = history_line(sn)
            else:
                skipped.append(sn)
                continue
            backup.append({"id": f["id"], "source_name": sn,
                           "content": content})
            conn.execute("UPDATE facts SET content = ? WHERE id = ?",
                         (line + "\n\n" + content, f["id"]))
            touched.append((f["id"], sn))
    if backup:
        with open(BACKUP, "w", encoding="utf-8") as fh:
            json.dump(backup, fh, indent=1)
    print(f"routed {len(touched)} docs (backup: {len(backup)} facts)")
    for fid, sn in touched:
        print(f"  [{fid}] {sn}")
    print(f"left alone (deliberate skips + already routed): {len(skipped)}")
    for sn in skipped:
        print(f"  skip: {sn}")


if __name__ == "__main__":
    main()
