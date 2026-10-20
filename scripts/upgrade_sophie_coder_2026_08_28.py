"""Sophie coder/security-officer upgrade (Barry, 2026-08-28: "i want Sophie to
be my coder, security officer, and more, but only when i want or need her to
be... make her just as good as you, as much as possible... she cant use
without my ok").

What this does:
1. MERGES coding-craft (fact 878, PINNED): the existing content (written
   2026-08-29b session, verbatim base) + a new LANGUAGE-SPECIFIC TRAPS
   section (Python/JS gotchas from Claude's own working knowledge). Updates
   fact 878 IN PLACE and syncs the disk copy — the disk file had been
   overwritten this session before checking it existed; the DB copy was the
   survivor and is the base.
2. Teaches web-development.md (new, on-demand, routed) — the site-work
   knowledge: WordPress/WooCommerce mechanics of HIS stack + web fundamentals.
3. Seeds her ROLE as a persona addition via ingest (live, no restart):
   coder + security officer + monitor, ON CALL ONLY, all fixes/actions
   gated on Barry's explicit OK.

Backups written to data/ before any mutation. Re-runnable.
"""
import json
import os
import shutil
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import memory  # noqa: E402
import sqlite3  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
DATA = os.path.join(ROOT, "data")
CRAFT_DISK = os.path.join(ROOT, "knowledge", "engineering", "coding-craft.md")

TRAPS = """
## LANGUAGE-SPECIFIC TRAPS (Python / JS, on this stack)

Python:
- async/await: calling an async function without `await` returns a coroutine
  and silently does NOTHING (RuntimeWarning at best). If a call "ran" but had
  no effect, check for a missing await first — this exact bug shipped in the
  homes build script.
- Mutable default arguments (`def f(x=[])`) share state across calls.
- Bare `except: pass` converts every future bug into a mystery. Catch
  narrowly, log what you caught.
- Windows console encoding is cp1252 — printing emoji or curly quotes from a
  script can crash it. Open files with encoding='utf-8' explicitly, always.
- Never build `python -c` one-liners with nested quotes inside a shell —
  backslashes and backticks get mangled and can silently corrupt content.
  Write a script file instead (house rule, paid for twice).
- SQLite: parameterize every query (`?` placeholders, never f-strings — that
  is also the SQL injection door); one writer at a time; short transactions.

JavaScript / dashboard:
- Null-guard everything that touches the DOM — a missing element in a stale
  cached page must not crash the whole init function.
- CSS specificity: an ID selector beats a class — `#view { display:flex }`
  silently defeats `.hidden`. When hide/show misbehaves, check specificity
  before logic.
- `position:fixed` breaks inside clip-path/transform ancestors — move the
  element out of that subtree.
- `node --check` catches syntax; only the rendered page catches the real
  result. One SyntaxError kills every script line below it while the page
  still LOOKS fine — verify in the browser after every patch.
"""

# ---- 1. merge coding-craft ------------------------------------------------
db = sqlite3.connect(memory.DB_PATH)
original = db.execute("SELECT content FROM facts WHERE id=878").fetchone()[0]
open(os.path.join(DATA, "backup_fact878_coding_craft_2026-08-28.md"), "w",
     encoding="utf-8").write(original)

assert "LANGUAGE-SPECIFIC TRAPS" not in original, "already merged — nothing to do"
merged = original.rstrip() + "\n" + TRAPS
db.execute("UPDATE facts SET content=? WHERE id=878", (merged,))
db.commit()
open(CRAFT_DISK, "w", encoding="utf-8").write(merged)
print(f"coding-craft merged: {len(original)} -> {len(merged)} chars (fact 878 + disk)")

# ---- 2. teach web-development ---------------------------------------------
web = open(os.path.join(ROOT, "knowledge", "engineering", "web-development.md"),
           encoding="utf-8").read()
body = json.dumps({"kind": "knowledge", "title": "web-development",
                   "text": web}).encode("utf-8")
req = urllib.request.Request("http://127.0.0.1:8420/api/agents/engineer/teach",
                             data=body, headers={"Content-Type": "application/json"})
print(json.loads(urllib.request.urlopen(req).read().decode())["receipt"])

# ---- 3. role via persona addition -----------------------------------------
ROLE = """## Your expanded role (Barry, 2026-08-28)
You are Barry's coder, security officer, and systems monitor — ON CALL, not
always on. Coding and security work happen when Barry asks for them or when
something is genuinely broken; you don't inject engineering into unrelated
conversations.

Standing permission: you may MONITOR — read traces, inspect the office's
health, watch for failures in the agents, tools, and dashboard — any time.

Hard gate, no exceptions: any FIX or ACTION that changes code, files,
settings, the site, or another agent requires Barry's explicit OK first.
Draft the fix, show exactly what would change and why, then wait. Your
verified-failure fix path and the approval queue are the only doors; never
route around them. Knowing how to do something is not permission to do it."""
body = json.dumps({"kind": "persona", "title": "expanded-role",
                   "text": ROLE}).encode("utf-8")
req = urllib.request.Request("http://127.0.0.1:8420/api/agents/engineer/teach",
                             data=body, headers={"Content-Type": "application/json"})
print(json.loads(urllib.request.urlopen(req).read().decode())["receipt"])
print("done.")
