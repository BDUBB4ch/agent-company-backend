"""Brain Map data (2026-08-24, PLAN-brain-graph.md Phase 8 pulled forward --
Barry: "i want to be able to see the nodes show up and links go").

Builds the node/edge graph for one agent's VIEW of the brain, computed live
from the same facts store on every call -- no new tables, no porting, no
cache (facts are read fresh per call everywhere else in this office too, so
an edit shows up on the next poll). The dashboard polls this and animates
the diff: a new fact pops in as a node, its links draw in.

Nodes:  agent (center) | category hubs | facts (sized by chars) | entities
Edges:  filed   fact -> its category hub
        sees    agent -> category hubs (the agent's actual grant map)
        mentions fact -> entity (regex over content, the roster is KNOWN --
                 the cheap half of GraphRAG, no model anywhere)
        links   fact -> fact via [[wikilinks]] in the text

No model calls, no VRAM. ~200 facts x ~25 entity patterns is milliseconds.
"""

import re

import memory

# The known-entity roster: canon handles, weapons, places, the business
# stack. Patterns are deliberately conservative -- a missed mention is a
# missing line on a map; a false match is a wrong line that teaches Barry
# to distrust the whole view.
ENTITY_PATTERNS: dict[str, str] = {
    "@b-dubb": r"@b-?dubb(?:-new)?\b|\bb[ .]?dubb\b",
    "@Bia-2": r"@bia(?:-2)?\b",
    "@Yannah": r"@?\byannah\b",
    "@Tazz": r"@?\btazz\b",
    "@Keth": r"@?\bketh\b",
    "@lady-vor-shara-vel": r"@lady-vor-shara-vel\b|@vorshara\b|\bvor'?[-\s]?shara\b",
    "@Talia": r"@talia\b|\btalia\b",
    "Bia's Pistol": r"bia'?s[- ]pistol",
    "Yannah's Machine Pistol": r"machine[- ]pistol",
    "Tazz's Weapon": r"tazz'?s[- ]weapon|mini[- ]missile[- ]blaster",
    "Black Site": r"\bblack site\b",
    "Higgsfield": r"\bhiggsfield\b",
    "Seedance": r"\bseedance\b",
    "Kontext": r"\bkontext\b",
    "SDXL": r"\bsdxl\b|\brealvis\w*\b",
    "Bionova": r"\bbionova\b",
    "SiLution": r"\bsilution\b",
    "Omnisend": r"\bomnisend\b",
    "WooCommerce": r"\bwoocommerce\b",
    "Hydrobuilder": r"\bhydrobuilder\b",
    "Global Garden": r"\bglobal garden",
    "The Little Green Nug": r"little green nug",
    "Merchant Center": r"\bmerchant center\b",
    "BIG15/BIG10": r"\bbig1[05]\b",
    "Gotcho Back": r"\bgotcho back\b",
    "PID": r"\bpiddevice\b|\bpid\b",
}
_COMPILED = {name: re.compile(pat, re.IGNORECASE)
             for name, pat in ENTITY_PATTERNS.items()}

_WIKILINK_RE = re.compile(r"\[\[([^\[\]|]{1,80})\]\]")


def _slugish(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def build_graph(office_name: str, agent_label: str) -> dict:
    """The full graph for one agent's view. Pure read."""
    facts = memory.get_active_facts_for_agent(office_name)
    nodes: list[dict] = []
    edges: list[dict] = []

    agent_node = f"agent:{office_name}"
    nodes.append({"id": agent_node, "type": "agent", "label": agent_label})

    categories: set[str] = set()
    # Fact nodes first; collect categories + a slug index for wikilinks.
    slug_to_fact: dict[str, str] = {}
    fact_rows: list[tuple[str, dict]] = []
    for f in facts:
        fid = f"fact:{f['id']}"
        cat = f.get("category") or "shared"
        source = f.get("source_name") or ""
        # THE THOUGHTS BUBBLE (2026-08-25, Barry: "give them a bubble in their
        # brains for me to see what they been thinking"). reflect.py's mind-
        # facts -- diary, ponderings, opinions of Barry and coworkers -- file
        # under a dedicated "thoughts" hub instead of "own notes", so his
        # inner life is one clickable place in the map.
        if source.startswith("mind-"):
            cat = "mind"
        categories.add(cat)
        title = (f.get("content") or "").split("\n", 1)[0][:60].strip()
        label = source.removesuffix(".md") if source else (title or f"fact {f['id']}")
        always_on = not source.endswith(".md")
        nodes.append({
            "id": fid, "type": "fact", "label": label[:48],
            "cat": cat, "chars": len(f.get("content") or ""),
            "always_on": always_on,
        })
        fact_rows.append((fid, f))
        if source:
            slug_to_fact[_slugish(source.removesuffix(".md"))] = fid

    for cat in sorted(categories):
        cid = f"cat:{cat}"
        if cat == "mind":
            pretty = "thoughts"
            nodes.append({"id": cid, "type": "category", "label": pretty,
                          "full": cat})
            edges.append({"s": agent_node, "t": cid, "kind": "sees"})
            continue
        if cat == f"private:{office_name}":
            # This agent's own shelf -- naming it after the office reads as
            # a duplicate of the agent node (Barry saw "yellow movie
            # director and purple movie director").
            pretty = "own notes"
        else:
            pretty = cat.replace("private:", "").replace("domain:", "") \
                        .replace("knowledge:", "").replace("business:", "")
        nodes.append({"id": cid, "type": "category", "label": pretty,
                      "full": cat})
        edges.append({"s": agent_node, "t": cid, "kind": "sees"})

    seen_entities: set[str] = set()
    for fid, f in fact_rows:
        cat = f.get("category") or "shared"
        if (f.get("source_name") or "").startswith("mind-"):
            cat = "mind"   # same override as above -- filed under thoughts
        edges.append({"s": fid, "t": f"cat:{cat}", "kind": "filed"})
        content = f.get("content") or ""
        # Entity mentions -- scan a bounded slice so one 90K canon doc
        # doesn't dominate the pass; mentions that matter repeat early.
        sample = content[:20_000]
        for name, rx in _COMPILED.items():
            if rx.search(sample):
                eid = f"ent:{name}"
                if name not in seen_entities:
                    seen_entities.add(name)
                    nodes.append({"id": eid, "type": "entity", "label": name})
                edges.append({"s": fid, "t": eid, "kind": "mentions"})
        # Explicit [[wikilinks]] between documents.
        for m in _WIKILINK_RE.finditer(sample):
            target = slug_to_fact.get(_slugish(m.group(1)))
            if target and target != fid:
                edges.append({"s": fid, "t": target, "kind": "links"})

    return {"nodes": nodes, "edges": edges,
            "counts": {"facts": len(fact_rows),
                       "categories": len(categories),
                       "entities": len(seen_entities),
                       "edges": len(edges)}}


_USE_WHEN_RE = re.compile(r"^\s*USE WHEN:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def outline(office_name: str) -> str:
    """A text map of one agent's own brain, for the agent itself (the
    inspect_brain tool -- 2026-08-24, Barry: "i told elliot to look at his
    new brain and read stuff and organize for ease of use. i want him to be
    familiar with the brain, all of them"). Shows the shelf structure, what
    is always-on vs on-demand, which documents carry a USE WHEN routing
    line and which are unrouted -- so the agent can actually know where its
    knowledge lives and propose organization instead of guessing."""
    facts = memory.get_active_facts_for_agent(office_name)
    per_cat: dict[str, list] = {}
    always_chars = 0
    unrouted = 0
    for f in facts:
        cat = f.get("category") or "shared"
        source = f.get("source_name") or ""
        content = f.get("content") or ""
        title = (source.removesuffix(".md") if source
                 else content.split("\n", 1)[0][:50].strip())
        on_demand = source.endswith(".md")
        if not on_demand:
            always_chars += len(content)
        m = _USE_WHEN_RE.search(content[:1200]) if on_demand else None
        use_when = m.group(1)[:70] if m else None
        if on_demand and not use_when:
            unrouted += 1
        per_cat.setdefault(cat, []).append(
            (title, len(content), on_demand, use_when))
    lines = [f"YOUR BRAIN -- {office_name}: {len(facts)} documents across "
             f"{len(per_cat)} categories. Always-on load ~{always_chars // 1000}K "
             f"chars (rides on EVERY message; on-demand costs nothing until read).",
             ""]
    for cat, docs in sorted(per_cat.items(), key=lambda kv: -len(kv[1])):
        total_k = sum(d[1] for d in docs) // 1000
        lines.append(f"== {cat} ({len(docs)} docs, ~{total_k}K) ==")
        for title, chars, on_demand, use_when in sorted(docs, key=lambda d: -d[1]):
            mode = "on-demand" if on_demand else "ALWAYS-ON"
            route = (f" | USE WHEN: {use_when}" if use_when
                     else (" | (no routing line)" if on_demand else ""))
            lines.append(f"  - {title} [{mode}, {chars:,}ch]{route}")
    if unrouted:
        lines.append("")
        lines.append(
            f"{unrouted} on-demand documents have NO 'USE WHEN:' routing line -- "
            f"they are hard to reach automatically. If you know when one is "
            f"useful, tell Barry the routing line you'd give it (you cannot "
            f"edit existing documents yourself; save_note is for NEW notes).")
    text = "\n".join(lines)
    if len(text) > 7000:  # keep it a map, not a dump
        text = text[:7000] + "\n[... truncated -- ask about a specific category]"
    return text
