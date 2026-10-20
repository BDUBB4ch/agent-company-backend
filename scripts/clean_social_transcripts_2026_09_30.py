"""Clean the broken conversation transcripts out of the agents' memories (2026-09-30).

Barry: "clean the diaries, back them up first". From 09-18 (thinking fully off for social talk) the
group chats / calls / visits copied each other: repeated passages and stacked "Name: Name:" labels.
Those transcripts were saved into each attendee's private memory:
  mind-groupchat-<date>.md   one chat per note        -> broken note deleted whole
  mind-dm-<who>-<month>.md   a month of visits/calls  -> only the broken visits removed, rest verbatim
Their diaries, reflections, talks with Barry and the CALLS/GROUP logs are NOT touched.

  python scripts/clean_social_transcripts_2026_09_30.py            dry run (counts only)
  python scripts/clean_social_transcripts_2026_09_30.py --apply    backup brain.db + JSON, then clean
"""
import json, os, re, sqlite3, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "brain.db")
BK = os.path.join(ROOT, "data", "backups")
APPLY = "--apply" in sys.argv

SENT = re.compile(r"(?<=[.!?])\s+")
STACKED = re.compile(r"(?m)^\s*\**\[?[A-Z][\w']+\]?\**:\s*\**\[?[A-Z][\w']+\]?\**:")
ENTRY = re.compile(r"(?m)^(?=\[20\d\d-\d\d-\d\d )")


def broken(text: str) -> tuple[bool, int, int]:
    s = [x.strip() for x in SENT.split(text) if len(x.strip()) > 40]
    reps = len(s) - len(set(s))
    labels = len(STACKED.findall(text))
    # one lone doubled label ("Elliot: Elliot: I'm here...") in an otherwise clean talk is a
    # cosmetic slip, not a broken memory -- that talk is kept as is
    return (reps >= 3 or labels >= 2), reps, labels


conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT * FROM facts WHERE source_name LIKE 'mind-groupchat-%' "
                    "OR source_name LIKE 'mind-dm-%'").fetchall()

deletes, updates, kept_notes, entries_cut, entries_kept = [], [], 0, 0, 0
for r in rows:
    c = r["content"]
    if r["source_name"].startswith("mind-groupchat-"):
        bad, reps, labels = broken(c)
        if bad:
            deletes.append(r)
        else:
            kept_notes += 1
        continue
    parts = ENTRY.split(c)
    head, entries = parts[0], parts[1:]
    good = [e for e in entries if not broken(e)[0]]
    entries_cut += len(entries) - len(good)
    entries_kept += len(good)
    if len(good) == len(entries):
        kept_notes += 1
    elif not good:
        deletes.append(r)
    else:
        updates.append((r, head + "".join(good).rstrip() + "\n"))

print(f"notes scanned {len(rows)} | delete whole {len(deletes)} | trim {len(updates)} | untouched {kept_notes}")
print(f"visit/call entries: cut {entries_cut}, kept {entries_kept}")
by_office = {}
for r in deletes + [u[0] for u in updates]:
    by_office[r["category"]] = by_office.get(r["category"], 0) + 1
print("notes changed per agent:", dict(sorted(by_office.items())))

if not APPLY:
    print("dry run -- nothing changed (add --apply)")
    sys.exit(0)

os.makedirs(BK, exist_ok=True)
db_bk = os.path.join(BK, "brain_before_social_clean_2026-09-30.db")
with sqlite3.connect(db_bk) as dst:
    conn.backup(dst)
js_bk = os.path.join(BK, "social_transcripts_before_clean_2026-09-30.json")
json.dump({"deleted": [dict(r) for r in deletes],
           "trimmed_before": [dict(u[0]) for u in updates]},
          open(js_bk, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("backups:", db_bk, js_bk)

with conn:
    for r in deletes:
        conn.execute("DELETE FROM facts WHERE id = ?", (r["id"],))
        conn.execute("DELETE FROM fact_vectors WHERE fact_id = ?", (r["id"],))
    for r, new in updates:
        conn.execute("UPDATE facts SET content = ? WHERE id = ?", (new, r["id"]))
        conn.execute("DELETE FROM fact_vectors WHERE fact_id = ?", (r["id"],))
print(f"applied: deleted {len(deletes)}, trimmed {len(updates)}")
