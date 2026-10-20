"""Office health check -- catches the drift that has actually bitten here.

Barry, 2026-08-23: "how do we prevent degredation?"

Every degradation in this build so far was INVISIBLE until output got bad:
the prompt cache silently broke and every reply re-read 50K tokens; 14 auto
-summaries crept onto the always-on shelf and pushed Elliot to 220K chars
until the 27B produced word salad; a runtime override left six seats on a
code-completion model for an unknown period; a canon sweep rewrote the one
document that must keep the old wording. None of those announced themselves.

This prints the numbers that move BEFORE quality drops. Run it when replies
feel off, after adding skills or facts, and after any model change:

    venv/Scripts/python.exe scripts/office_health.py

Read-only: it measures, it never edits.
"""
import pathlib
import re
import sqlite3
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import agents
import memory

# Elliot degraded into word salad around 220K chars of system prompt; the
# task-scoped rebuild that fixed it lands ~45K. Warn well before the cliff.
ALWAYS_ON_WARN = 140_000
ALWAYS_ON_FAIL = 190_000
HISTORY_WARN = 30
EXEMPLAR_WARN = 12_000

flags = []


def check_models():
    print("== MODELS (what each seat RESOLVES to, not what the docs claim) ==")
    try:
        import main as _m
        overrides = memory.get_agent_model_overrides()
    except Exception as e:
        print(f"  (could not read overrides: {e})")
        overrides = {}
    backend, model = memory.get_active_generation() if hasattr(
        memory, "get_active_generation") else ("?", "?")
    print(f"  global: {backend} / {model}")
    parked = [k for k, v in (overrides or {}).items() if v is None]
    if parked:
        flags.append(f"seats parked on None (follow-the-global footgun): {parked}")
    if overrides:
        print(f"  runtime overrides: {overrides}")
    else:
        print("  runtime overrides: (empty -- correct)")


def check_prompts():
    print("\n== ALWAYS-ON LOAD PER AGENT (persona + pins + brain) ==")
    for agent_id, a in agents.AGENTS.items():
        office = a["office_name"]
        pins = agents.pinned_skills_for(agent_id)
        try:
            pin_block = memory.pinned_skills_block(office, pins)
            brain = memory.brain_context_block(
                office, include_shared=a.get("business_context", True),
                pinned_titles=pins)
        except Exception as e:
            print(f"  {a['name']:22} ERROR {e}")
            continue
        persona = len(a["system_prompt"])
        total = persona + len(pin_block) + len(brain)
        mark = "  "
        if total >= ALWAYS_ON_FAIL:
            mark = "!!"; flags.append(f"{a['name']} always-on {total:,} chars -- past the word-salad threshold")
        elif total >= ALWAYS_ON_WARN:
            mark = "? "; flags.append(f"{a['name']} always-on {total:,} chars -- creeping up")
        print(f"{mark}{a['name']:22} total {total:>8,}  "
              f"(persona {persona:,} + pins {len(pin_block):,} + brain {len(brain):,}, {len(pins)} pins)")
        if "skipped" in pin_block.lower()[:600]:
            flags.append(f"{a['name']}: a pinned skill was SKIPPED -- over pin budget")


def check_always_on_creep():
    print("\n== AUTO-SUMMARY CREEP (the thing that bloated Elliot) ==")
    con = sqlite3.connect(REPO / "data" / "brain.db")
    rows = con.execute(
        "SELECT category, COUNT(*), SUM(LENGTH(content)) FROM facts "
        "WHERE status='active' AND (source_name IS NULL OR source_name NOT LIKE '%.md') "
        "AND (source_name LIKE '%summar%' OR source_name LIKE '%conversation%') "
        "GROUP BY category ORDER BY 3 DESC").fetchall()
    if not rows:
        print("  none riding always-on -- good")
    for cat, n, chars in rows:
        print(f"  {cat:28} {n:>3} summaries  {chars or 0:>8,} chars ALWAYS-ON")
        if (chars or 0) > 20_000:
            flags.append(f"{cat}: {chars:,} chars of auto-summaries always-on -- "
                         f"move them to .md (on-demand), as done 2026-08-21")


def check_history():
    print("\n== CONVERSATION DEPTH (stale detail echoes from history) ==")
    con = sqlite3.connect(REPO / "data" / "brain.db")
    for aid, n in con.execute(
            "SELECT agent_id, COUNT(*) FROM conversations GROUP BY agent_id "
            "ORDER BY 2 DESC").fetchall():
        mark = "? " if n > HISTORY_WARN else "  "
        print(f"{mark}{aid:16} {n:>4} turns")
        if n > HISTORY_WARN:
            flags.append(f"{aid}: {n} turns of history -- clear it if wrong "
                         f"details start repeating (memory.clear_conversation)")


def check_exemplars():
    print("\n== ELLIOT'S APPROVED-PROMPT CORPUS ==")
    found = False
    for f in memory.get_active_facts_for_agent("MovieDirector"):
        if f.get("source_name") == "prompt-exemplars.md":
            found = True
            n = f["content"].count("--- APPROVED ---")
            size = len(f["content"])
            print(f"  {n} approved prompts, {size:,} chars")
            if size > EXEMPLAR_WARN:
                flags.append(f"exemplar corpus {size:,} chars -- prune the weakest")
            print("  (a weak exemplar COMPOUNDS -- read them occasionally and "
                  "delete any that are not the standard)")
    if not found:
        print("  none yet -- tell Elliot 'perfect' or 'save that' on a prompt "
              "you like and it starts building")


def check_build_map():
    """2026-10-10 (Barry: "missing 17 of 90, is crazy"): Sophie's BUILD MAP went 12 days without the modules added
    after it -- her own engineer_ops / stack_watch among them. Every backend module must be named in it."""
    print("\n== SOPHIE'S BUILD MAP COVERAGE ==")
    con = sqlite3.connect(REPO / "data" / "brain.db")
    row = con.execute("SELECT content FROM facts WHERE status='active' AND category='private:Engineer' AND "
                      "source_name='build-map-custodian-subsystems-modules-logs-where-the-truth-lives.md'").fetchone()
    if not row:
        flags.append("Sophie's BUILD MAP is missing from her shelf")
        print("  MISSING")
        return
    named = set(re.findall(r"\b([a-z_0-9]+)\.py\b", row[0]))
    mods = sorted(p.stem for p in (REPO / "backend").glob("*.py"))
    missing = [m for m in mods if m not in named]
    print(f"  {len(mods) - len(missing)} of {len(mods)} backend modules named")
    if missing:
        flags.append(f"Sophie's BUILD MAP does not name {len(missing)} module(s): {', '.join(missing)} -- "
                     f"add them (scripts/teach_sophie_2026_10_10.py)")


def main():
    print("OFFICE HEALTH\n" + "=" * 60)
    check_models()
    check_prompts()
    check_always_on_creep()
    check_history()
    check_exemplars()
    check_build_map()
    print("\n" + "=" * 60)
    if flags:
        print("FLAGS:")
        for f in flags:
            print("  * " + f)
    else:
        print("No drift detected.")


if __name__ == "__main__":
    main()
