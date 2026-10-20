"""Verify V10 is live and that the @handle / voice-id machinery still works.

Barry, 2026-09-20: "make sure elliot still uses the @'s and id's properly."
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import jobs  # noqa: E402
import script_index  # noqa: E402
import script_wip  # noqa: E402

OFFICE = "MovieDirector"
FAILS = []


def check(label, ok, detail=""):
    print(("[PASS] " if ok else "[FAIL] ") + label + (f"  {detail}" if detail else ""))
    if not ok:
        FAILS.append(label)


print("=== 1. the script resolves ===")
scripts = script_index.list_scripts(OFFICE)
names = [s["title"] for s in scripts]
# titles have .md stripped by memory._skill_title
TITLE = script_wip.WIP_SOURCE.removesuffix(".md")
check("V10 is discoverable as a script", TITLE in names, str(names))
check("no v7/v8/v9 script left", not any(re.search(r"v[789]", n, re.I) for n in names))
check("default_script resolves to V10",
      script_index.default_script(OFFICE) == TITLE,
      script_index.default_script(OFFICE))
check("DEFAULT_SCRIPT constant matches the real title",
      script_index.DEFAULT_SCRIPT == TITLE, script_index.DEFAULT_SCRIPT)

print()
print("=== 2. the shots he was getting wrong ===")
for ask, expect in (("shot 2", "THE CALL"), ("shot 3", "THE RUN"), ("shot 0", "THE BRIDGE")):
    parsed = jobs.parse_shot_list(ask)
    out = script_index.read_scene(OFFICE, parsed[0][0] + " " + parsed[0][1])
    body = out.get("text") or out.get("content") or "" if isinstance(out, dict) else str(out)
    check(f"{ask!r} -> {expect}", expect in body[:200], body.split("\n")[0][:60])

print()
print("=== 3. no duplicate shot numbers any more ===")
text = ""
import sqlite3, glob
cands = glob.glob(os.path.join(ROOT, "data", "*.db"))
db = [c for c in cands if "brain" in os.path.basename(c)] or cands
cur = sqlite3.connect(db[0]).cursor()
cur.execute("select content from facts where source_name=? and status='active'",
            (script_wip.WIP_SOURCE,))
text = cur.fetchone()[0]
labels = re.findall(r"^((?:SHOT|B-ROLL)\s+\d+)\b", text, re.M)
dupes = sorted({l for l in labels if labels.count(l) > 1})
check("zero duplicate shot labels", not dupes, str(dupes))
check("zero lettered second track",
      not re.search(r"^(?:SHOT|B-ROLL)\s+\d+[A-Z]\b", text, re.M))

print()
print("=== 4. handles and voice ids inside V10 ===")
handles = re.findall(r"@[A-Za-z][\w'\-]*", text)
check("handles present", len(handles) > 200, f"{len(handles)} handle mentions")
retired = [h for h in set(handles) if h in ("@Bia", "@BDUBB", "@B-DUBB-new", "@Vorshara")]
check("no retired handles", not retired, str(retired))

ROSTER = {
    "@b-dubb": "9b162037-e549-4065-9562-ebac293ee72a",
    "@Bia-2": "f32c8f51-449e-4ddf-bdf7-1527e11df917",
    "@Yannah": "032386ec-491b-5bdc-81ac-49e9a6a2c89d",
    "@Tazz": "3811e986-0891-47cf-a1f5-78a1d62a547a",
    "@Keth": "6b528d43-c056-4a2f-9d82-1591a7ba13b0",
    "@lady-vor-shara-vel": "d081b915-6623-4a44-bacf-80d0f1c90a03",
}
for handle, vid in ROSTER.items():
    check(f"{handle} voice id in V10", vid in text)

print()
print("=== 5. the brief still tells him both rules ===")
dump = os.path.join(ROOT, "data", "_shot_directive_dump.txt")
if os.path.exists(dump):
    d = open(dump, encoding="utf-8").read()
    check("@HANDLES rule in the brief", "@HANDLES ON EVERYTHING HE OWNS" in d)
    check("every-mention rule", "EVERY MENTION" in d)
    check("voice-id rule in the brief", "EVERY SPEAKING LINE CARRIES ITS VOICE ID" in d)
    # the dump holds SOURCE literals, so newlines appear as the two characters
    # backslash-n, not as real newlines -- count the escaped form
    roster_lines = d.count("\\n  @")
    check("roster is one-per-line", roster_lines >= 6, f"{roster_lines} lines")
    check("told it is his job", "GETTING IT RIGHT IS ON YOU" in d)
    for handle, vid in ROSTER.items():
        check(f"{handle} id in the brief", vid in d)
else:
    check("directive dump exists", False, "run scripts/_dump_shot_directive.py")

print()
print(f"{'ALL PASS' if not FAILS else str(len(FAILS)) + ' FAILED: ' + '; '.join(FAILS)}")
sys.exit(1 if FAILS else 0)
