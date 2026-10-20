"""Seed the knowledge files written 2026-10-11 (AI Skills, agent testing, WordPress, film craft, herbal-video craft).
Barry: "figure out whats needed for my agents" / "cover the gaps". Validates each file first (USE WHEN on line 1, no
outside-service words outside the credit line), then supersede-and-add like _seed_knowledge.py. Safe to re-run.
Folder -> shelf: operations/marketing/creative/engineering/business_ops/leadership/legal -> domain:<folder>;
film_craft -> private:MovieDirector (Elliot); herbal_video_craft -> private:ilnora.
Usage: python scripts/seed_new_skills_2026_10_11.py [--dry]"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import memory

SINCE = float(os.environ.get("SEED_SINCE", "0")) or 1791779000.0     # 2026-10-11 ~22:30 local (after the last seeded batch)
DRY = "--dry" in sys.argv
SHELVES = {"operations": "domain:operations", "marketing": "domain:marketing", "creative": "domain:creative",
           "engineering": "domain:engineering", "business_ops": "domain:business_ops", "leadership": "domain:leadership",
           "legal": "domain:legal", "film_craft": "private:MovieDirector", "herbal_video_craft": "private:ilnora"}
BAD = re.compile(r"(?i)\b(shopify|hubspot|salesforce|google (?:drive|calendar|docs|sheets)|slack|zapier|stripe|"
                 r"canva|figma|claude code|subagent|datarobot|zizi|recraft|tabler|mcp server)\b")

memory.init_db()
ok, bad = 0, []
for folder, category in SHELVES.items():
    d = os.path.join(ROOT, "knowledge", folder)
    if not os.path.isdir(d):
        continue
    for name in sorted(os.listdir(d)):
        p = os.path.join(d, name)
        if not (name.endswith(".md") and os.path.isfile(p)) or os.path.getmtime(p) < SINCE:
            continue
        text = open(p, encoding="utf-8").read()
        lines = text.split("\n")
        problems = []
        if not lines[0].startswith("USE WHEN:"):
            problems.append("line 1 is not USE WHEN")
        body = "\n".join(lines[5:])
        m = BAD.search(body)
        if m:
            problems.append(f"mentions {m.group(0)!r}")
        if len(text) < 1500:
            problems.append(f"only {len(text)} chars")
        if problems:
            bad.append((folder, name, problems))
            continue
        if not DRY:
            with memory.get_db() as conn:
                conn.execute("UPDATE facts SET status='superseded' WHERE category=? AND source_name=? AND status='active'",
                             (category, name))
            memory.add_fact(category, text, name)
        ok += 1
        print(("would seed" if DRY else "seeded"), category, name, len(text))
print(f"\n{ok} {'valid' if DRY else 'seeded'}; {len(bad)} held back")
for f, n, pr in bad:
    print("  HELD", f, n, pr)
