"""Handle sweep of EP1 V9A.1 -- Barry, 2026-09-16: "make sure the handles are good as well".

WHY: the script had @Talia ZERO times and "The Talia" six times, plus ~60 other bare
mentions. A handle is what binds Barry's real Higgsfield element; the same name in
plain prose binds nothing and the generator invents its own version -- which is
exactly what happened on the B-ROLL 00 render.

WHAT THIS DOES NOT TOUCH, deliberately:
  * SPOKEN DIALOGUE. A handle never goes inside words a character says out loud.
    Any line whose stripped form starts with a quote is skipped entirely.
  * The document header / changelog (the first block, before the first shot).
  * The VOICE REFERENCE table rows (lines starting with "|") -- reference, not prompt.
  * A name in quotes being read as a name: EXPRESSION says  the name "Keth" carries
    weight  -- that is Bia reading a word, not a character in frame. Any occurrence
    immediately wrapped in quotes is skipped.
  * ALL-CAPS slugs and titles (TALIA CREW, THE TALIA) -- matching is case-sensitive
    on purpose, so headers and slug formatting are left exactly as Barry wrote them.

Order matters: the longest name first, so "Lady Vor'Shara Vel" is not half-replaced
by the "Vor'Shara" rule.

Backup: data/script_backups/v9A.1_before_handle_sweep_2026-09-16.md
Revert = write that file back over fact 2282 and the Downloads copy.
"""
import os
import re
import sqlite3
import sys

DB = os.path.join(os.path.dirname(__file__), "..", "data", "brain.db")
DISK = r"C:\Users\Owner\Downloads\TALIA_CREW_EP1_PRODUCTION_V9A.1.md"
BACKUP = os.path.join(os.path.dirname(__file__), "..", "data", "script_backups",
                      "v9A.1_before_handle_sweep_2026-09-16.md")
FACT_ID = 2282

# Longest first. Case-sensitive by design (see docstring).
HANDLES = [
    ("Lady Vor'Shara Vel", "@lady-vor-shara-vel"),
    ("Vor'Shara Vel", "@lady-vor-shara-vel"),
    ("Vor'Shara", "@lady-vor-shara-vel"),
    ("B Dubb", "@b-dubb"),
    ("Talia", "@Talia"),
    ("Yannah", "@Yannah"),
    ("Tazz", "@Tazz"),
    ("Keth", "@Keth"),
    ("Bia", "@Bia-2"),
]


def sweep_line(line):
    """Replace bare names with handles in ONE line. Returns (new_line, n)."""
    total = 0
    for name, handle in HANDLES:
        # not already handled (no @ or - before), not part of a longer word,
        # and not immediately wrapped in double quotes.
        pat = re.compile(
            r'(?<![@\w\'-])' + re.escape(name) + r'(?![\w-])')

        def repl(m):
            s, e = m.start(), m.end()
            before = line[s - 1] if s else ""
            after = line[e] if e < len(line) else ""
            if before in '"\u201c' and after in '"\u201d':
                return m.group(0)          # the name "Keth" -- leave it
            return handle

        line, n = pat.subn(repl, line)
        total += n
    return line, total


def main():
    con = sqlite3.connect(DB)
    text = con.execute(
        "select content from facts where id=?", (FACT_ID,)).fetchone()[0]

    os.makedirs(os.path.dirname(BACKUP), exist_ok=True)
    with open(BACKUP, "w", encoding="utf-8") as fh:
        fh.write(text)

    disk_matched = False
    if os.path.exists(DISK):
        with open(DISK, encoding="utf-8") as fh:
            disk_matched = fh.read() == text

    lines = text.split("\n")
    # The header/changelog ends at the first shot separator.
    first_block = next((i for i, l in enumerate(lines)
                        if l.strip().startswith(("B-ROLL", "SHOT "))), 0)

    changed, skipped_dialogue, skipped_table, examples = 0, 0, 0, []
    for i, line in enumerate(lines):
        s = line.strip()
        if i < first_block:
            continue
        if s.startswith('"') or s.startswith("\u201c"):
            skipped_dialogue += 1
            continue
        if s.startswith("|"):
            skipped_table += 1
            continue
        new, n = sweep_line(line)
        if n:
            changed += n
            if len(examples) < 10:
                examples.append((i, s[:90], new.strip()[:90]))
            lines[i] = new

    out = "\n".join(lines)
    print("handles written: %d" % changed)
    print("lines skipped -- dialogue: %d, table rows: %d, header lines: %d"
          % (skipped_dialogue, skipped_table, first_block))
    print()
    for i, b, a in examples:
        print("  %4d  - %s" % (i, b))
        print("        + %s" % a)
    print()
    print("chars %d -> %d" % (len(text), len(out)))

    con.execute("update facts set content=? where id=?", (out, FACT_ID))
    con.commit()
    con.close()

    if disk_matched:
        with open(DISK, "w", encoding="utf-8") as fh:
            fh.write(out)
        print("disk copy updated (byte-identical before)")
    elif os.path.exists(DISK):
        print("WARNING: disk copy differed -- NOT touched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
