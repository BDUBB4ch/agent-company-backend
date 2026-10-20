"""Capture Barry's standing instructions so he never repeats them.

WHY THIS EXISTS
---------------
Barry, 2026-08-16: "i dont want to have to keep reminding my agents about
things all the time." He was right that they forget: a correction given in
chat lives in the 20-message history window and then dies -- the learning
loop only fires on approval decisions, never on what he SAYS. Every
standing rule that ever stuck in this office stuck because someone edited
a prompt or the canon in a code session. This module closes that gap at
the chat layer: when a message to an agent is shaped like a standing
instruction, it is written into that agent's private brain as a permanent
always-on rule.

DESIGN RULES:
  - HIS WORDS, VERBATIM. No model ever summarizes a rule -- summarizing
    his words is how canon got mangled (see the 2026-08-08 incident). The
    fact is his sentence with a STANDING RULE header, nothing else.
  - Deterministic detection, conservative on purpose. A false capture is
    a junk fact he has to notice and delete; a missed capture costs one
    repeat. So detection requires an explicit instruction marker, not
    vibes. Misses are acceptable, noise is not.
  - Always-on (no .md source_name): a rule that has to be recalled to be
    obeyed isn't a rule. Rules are short -- his sentence -- so the
    per-message cost is tens of chars, not thousands.
  - Deduplicated: repeating the same instruction (the exact behaviour
    that frustrates him) must not create a second copy.
  - Everything is logged and visible in the dashboard's Brain tab, where
    any rule can be deleted.
"""

import datetime
import re

import memory

# A standing instruction announces itself. Each pattern is an explicit
# durable-instruction marker -- questions and one-off requests match none
# of them.
_RULE_PATTERNS = [
    re.compile(r"\bfrom now on\b", re.I),
    re.compile(r"\bevery time\b", re.I),
    re.compile(r"\bfrom here on( out)?\b", re.I),
    re.compile(r"\bgoing forward\b", re.I),
    re.compile(r"\bremember to\b", re.I),
    re.compile(r"\bremember:\s", re.I),
    re.compile(r"\bi('ve| have)? (already )?told you\b", re.I),
    # "how many times do I have to..." is a repeated-correction marker;
    # "how many times does Bia fire" is a story question. The pronoun is
    # the difference.
    re.compile(r"\bhow many times (do|must|have) i\b", re.I),
    # Any "stop <gerund>" -- "stop changing my shit" is a real Barry
    # correction and a fixed verb list missed it. "stop by the store"
    # stays uncaptured because "by" is not a gerund.
    re.compile(r"\bstop \w+ing\b", re.I),
    re.compile(r"\bdon'?t (ever|even)?\s*\w+ (that |this |it )?(again|anymore)\b", re.I),
    # "always"/"never" only count with an instruction verb right after --
    # "is he always late?" must not match.
    re.compile(r"\b(always|never) (be|use|write|include|keep|check|ask|start|"
               r"end|open|close|put|add|say|call|show|give|do|make|assume|"
               r"describe|mention|answer|wrap|turn)\b", re.I),
]

# Instructions are short. A long message is a brief or a story beat, and
# capturing it whole would bloat the brain -- the exact failure the
# 2026-08-03 cleanup existed to undo.
_MAX_RULE_CHARS = 500

_SOURCE = "standing-rule"  # no .md -> always-on by definition

# Soft ceiling: past this, new rules still save (losing one costs Barry a
# repeat) but the log calls for a cleanup pass -- the consolidation phase
# owns actually pruning.
_SOFT_CAP = 25


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def looks_like_rule(message: str) -> bool:
    if not message or len(message) > _MAX_RULE_CHARS:
        return False
    return any(p.search(message) for p in _RULE_PATTERNS)


def capture(office_name: str, message: str) -> str | None:
    """Save a standing instruction to this agent's private brain.

    Returns the stored content when captured, None otherwise. Never
    raises -- a capture failure must never cost the chat turn.
    """
    try:
        if not looks_like_rule(message):
            return None

        # Dedup against every rule already stored for this agent: if his
        # sentence is already on file (or contained in a stored rule),
        # repeating it must not double it.
        norm = _normalize(message)
        for fact in memory.get_active_facts_for_agent(office_name):
            if (fact.get("source_name") or "") == _SOURCE:
                if norm and norm in _normalize(fact.get("content") or ""):
                    return None

        date = datetime.date.today().isoformat()
        content = (
            f"STANDING RULE from Barry ({date}) -- follow this in every "
            f"conversation, it is not a suggestion:\n\"{message.strip()}\""
        )
        memory.add_fact(
            category=f"private:{office_name}",
            content=content,
            source_name=_SOURCE,
            title=f"STANDING RULE {date}",
        )

        count = sum(1 for f in memory.get_active_facts_for_agent(office_name)
                    if (f.get("source_name") or "") == _SOURCE)
        if count > _SOFT_CAP:
            print(f"[standing-rules] {office_name} now has {count} rules -- "
                  f"time for a consolidation pass")
        return content
    except Exception as exc:
        print(f"[standing-rules] capture failed for {office_name}: {exc}")
        return None
