"""THE LENGTH NET BATTERY (2026-09-20).

Barry: "shit Elliot gave me a super long Shot 00" -> then, after the first
(prompt-only) fix, "no, elliots last shot 01 was longer."

Run this after ANY change to _SHOT_FIELD_CAPS, _SHOT_FENCE_CAP,
_SHOT_FIELD_RE, _shot_field_sizes or _shot_length_gaps.

It measures against REAL texts, not invented ones:
  - Barry's own authored SHOT 01 from the live V9A.1 script  -> must be CLEAN
  - conversation 2519 (09-20 00:50, the 9,314-char reply)    -> must FIRE
  - conversation 2521 (09-20 01:15, the 13,832 after fix 1)  -> must FIRE

No GPU, no model call -- safe to run during a render.
"""
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "brain.db")

# Load the three functions out of main.py without importing it (main.py is the
# app entry point -- importing it would build a second copy of the module and
# re-run its module level; see the 2026-09-19 note in CLAUDE.md).
src = open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read()
start = src.index("_SHOT_FIELD_CAPS")
end = src.index("def _lesson_claim_gaps")
ns = {"re": re, "_IMAGE_FENCE_RE": re.compile(r"```image\s*\n(.*?)```", re.DOTALL)}
exec(src[start:end], ns)  # noqa: S102 -- lifting our own source, not input
field_sizes = ns["_shot_field_sizes"]
length_gaps = ns["_shot_length_gaps"]


def barry_shot_01(conn) -> str:
    row = conn.execute(
        "select content from facts where source_name='ep1-production-v9A.1-WIP.md' "
        "and status='active'").fetchone()
    m = re.search(r"(?ms)(SHOT 01\b.*?)(?=\nSHOT 0?2\b|\nB-ROLL)", row[0])
    return m.group(1) if m else ""


def main() -> int:
    conn = sqlite3.connect(DB)
    cases = [("BARRY'S OWN SHOT 01", barry_shot_01(conn), False)]
    for cid in (2519, 2521):
        row = conn.execute(
            "select content from conversations where id=?", (cid,)).fetchone()
        if row:
            cases.append((f"conversation {cid}", row[0], True))

    failures = 0
    for name, text, should_fire in cases:
        gaps = length_gaps(text)
        fired = bool(gaps)
        ok = fired == should_fire
        failures += 0 if ok else 1
        print(f"[{'PASS' if ok else 'FAIL'}] {name} -- {len(text)} chars, "
              f"{'fires' if fired else 'clean'} (expected "
              f"{'fires' if should_fire else 'clean'})")
        for k, v in sorted(field_sizes(text).items()):
            cap = ns["_SHOT_FIELD_CAPS"].get(k)
            print(f"         {k}: {v}" + (f" / {cap}" if cap else ""))
        for g in gaps:
            print(f"         -> {g}")

    print(f"\n{len(cases) - failures}/{len(cases)} pass")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
