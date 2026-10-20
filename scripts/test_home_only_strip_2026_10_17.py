"""2026-10-17: a "## ... HOME ONLY ..." section in a personality file must never reach a WORK prompt.
Pulls main._without_home's source out of backend/main.py (importing main builds the app) and runs it over every
personality file: the HOME ONLY sections are gone at work, everything before them is kept, and the home side
(the raw file) still has them. No backend, no model. Exit 1 on any failure."""
import ast
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read()
tree = ast.parse(src)
node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_without_home")
pat = next(n for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "_HOME_LIFE_RE")
ns = {"re": re}
exec(ast.get_source_segment(src, pat), ns)
exec(ast.get_source_segment(src, node), ns)
without_home = ns["_without_home"]

fails = []
n_sections = 0
for path in sorted(glob.glob(os.path.join(ROOT, "personalities", "*.md"))):
    raw = open(path, encoding="utf-8").read()
    work = without_home(raw)
    name = os.path.basename(path)
    secs = [m.start() for m in re.finditer(r"(?im)^#+ .*home only", raw)]
    n_sections += len(secs)
    if "home only" in work.lower():
        fails.append(f"{name}: a HOME ONLY heading survived at work")
    for m in re.finditer(r"(?im)^#+ .*home only.*$", raw):
        body = raw[m.end():]
        nxt = re.search(r"(?m)^#", body)
        body = body[:nxt.start()] if nxt else body
        probe = [s for s in re.split(r"(?<=[.!?])\s+", body.strip()) if len(s) > 40][:3]
        for s in probe:
            if s[:60] in work:
                fails.append(f"{name}: a HOME ONLY sentence survived at work: {s[:50]!r}")
    if secs:
        before = raw[:secs[0]]
        first_kept = next((s for s in re.split(r"(?<=[.!?])\s+", before) if len(s) > 40 and not ns["_HOME_LIFE_RE"].search(s)), "")
        if first_kept and first_kept[:60] not in work:
            fails.append(f"{name}: a normal sentence before the section was LOST at work: {first_kept[:50]!r}")
    print(f"{name}: raw {len(raw)} chars, work {len(work)} chars, HOME ONLY sections {len(secs)}")
print(f"sections found: {n_sections}")
print("RESULT:", "PASS" if not fails and n_sections >= 6 else "FAIL: " + "; ".join(fails or ["fewer than 6 sections"]))
sys.exit(1 if fails or n_sections < 6 else 0)
