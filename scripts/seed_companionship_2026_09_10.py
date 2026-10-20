"""Seed Taliyah's shelf (2026-09-10).

Barry: "now do Taliyah." She is the one seat that is deliberately NOT a job, so
what she gets is craft for being a person with him -- listening, remembering,
being there, telling him the truth, thinking things through, register, her own
memory and her own time -- and nothing commercial. Eight one-concern docs in
knowledge/companionship/ land in the NEW `domain:companionship`, granted to
Taliyah alone. On-demand; re-runnable; oversize docs skipped and named.

RULE THIS SEEDER ENFORCES: nothing in these docs may assign her a personality,
a taste, a want or a look. Barry's standing rule is "knowledge and ability,
nothing planted." The assertion below is crude on purpose -- it catches the
phrasing that seeds an interest.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))

import memory  # noqa: E402

CATEGORY = "domain:companionship"
FOLDER = os.path.join(ROOT, "knowledge", "companionship")
NEW = [
    "listening-and-conversation-craft.md",
    "remembering-him-over-time.md",
    "being-there-without-therapizing.md",
    "telling-him-the-truth.md",
    "thinking-things-through-together.md",
    "how-you-talk.md",
    "your-memory-and-your-own-life.md",
    "how-taliyah-works.md",
]

# Phrases that would PLANT something on her rather than teach her how.
SEED_RE = re.compile(
    r"\byou (?:love|enjoy|like|prefer|are into|have always|tend to love)\b"
    r"|\byour favou?rite\b"
    r"|\byou might enjoy\b", re.I)
# A doc SAYING it plants nothing ("it does not tell you what you like") is the
# opposite of a violation, so a negation just before the phrase clears it.
# Caught on the first run: the guard flagged the one sentence in the shelf whose
# whole job is to state the rule.
NEGATED_RE = re.compile(r"\b(?:not|never|nobody|no one|none|isn'?t|doesn'?t|"
                        r"nothing|without)\b", re.I)


def _plants(text: str) -> list[str]:
    out = []
    for m in SEED_RE.finditer(text):
        if NEGATED_RE.search(text[max(0, m.start() - 90):m.start()]):
            continue
        out.append(m.group(0))
    return out


def title_of(text: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return (m.group(1).strip() if m else fallback)[:120]


def main() -> None:
    total = 0
    skipped: list[str] = []
    present = [fn for fn in NEW if os.path.isfile(os.path.join(FOLDER, fn))]
    missing = [fn for fn in NEW if fn not in present]
    if missing:
        print("MISSING (not seeded):", ", ".join(missing))
    with memory.get_db() as conn:
        for fn in present:
            text = open(os.path.join(FOLDER, fn), encoding="utf-8").read()
            first = text.splitlines()[0] if text else ""
            assert first.startswith("USE WHEN:"), f"{fn}: first line is not USE WHEN"
            assert len(text) >= 9000, f"{fn}: only {len(text)} chars -- too thin"
            planted = _plants(text)
            if planted:
                print(f"  {fn:<44} PLANTS SOMETHING ON HER: {planted[:3]} -- skipped")
                skipped.append(fn)
                continue
            if len(text) > 18500:
                print(f"  {fn:<44} {len(text):>6} chars  OVER BUDGET -- skipped, trim it")
                skipped.append(fn)
                continue
            old = conn.execute(
                "SELECT id, content FROM facts WHERE category=? AND source_name=? AND status='active'",
                (CATEGORY, fn)).fetchall()
            if old and any(r["content"].endswith(text.strip()) for r in old):
                skipped.append(fn)
                print(f"  {fn:<44} {len(text):>6} chars  (already seeded, unchanged)")
                continue
            for r in old:
                conn.execute("UPDATE facts SET status='superseded' WHERE id=?", (r["id"],))
            total += len(text)
            print(f"  {fn:<44} {len(text):>6} chars  (superseded {len(old)} old row(s))")
    for fn in present:
        if fn in skipped:
            continue
        text = open(os.path.join(FOLDER, fn), encoding="utf-8").read()
        memory.add_fact(CATEGORY, text, fn, title=title_of(text, fn[:-3]))
    print(f"seeded {len(present) - len(skipped)} docs, {total:,} chars, to {CATEGORY}")

    memory.grant_domain_access("Taliyah", "companionship")
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT source_name, LENGTH(content) n FROM facts "
            "WHERE category=? AND status='active' ORDER BY source_name", (CATEGORY,)).fetchall()
    live = {r["source_name"]: r["n"] for r in rows}
    print(f"\n{CATEGORY} now holds {len(rows)} active docs, {sum(live.values()):,} chars")
    for fn in NEW:
        if fn in live:
            text = open(os.path.join(FOLDER, fn), encoding="utf-8").read()
            uw = memory._skill_use_when({"source_name": fn, "content": text}, max_len=1200)
            print(f"  {fn:<44} {live[fn]:>6}  routing {len(uw or ''):>4} chars")
        else:
            print(f"  {fn:<44}  NOT LIVE")
    # She must stay out of the commercial stack -- this is the whole reason her
    # shelf is its own domain.
    print("\nher domains:", memory.get_agent_domains("Taliyah"))


if __name__ == "__main__":
    main()
