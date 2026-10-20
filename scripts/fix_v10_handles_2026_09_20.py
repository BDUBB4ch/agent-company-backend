r"""Fix the two remaining V10 defects, and show every change for review.

Barry, 2026-09-20: "you fix it and give me something to give sintra to fix on
her end."

1. BACKSLASH ESCAPES inside @handles. Her .md export escapes underscores and
   asterisks, so @loc_hidden-black-site becomes @loc\_hidden-black-site and
   @Bia's-Pistol* becomes @Bia's-Pistol\*. A handle with a backslash in it
   binds nothing. Scoped to @handle tokens ONLY -- a legitimate markdown escape
   anywhere else in his prose is left alone.
   ⚠️ THE STAR STAYS on @Bia's-Pistol* -- Barry, 2026-09-20: "oh no leave the
   star." Only the backslash comes off.

2. PLAIN NAMES in CAMERA lines and action prose -> their @handle.
   ⚠️ NEVER INSIDE QUOTED SPEECH. Vor'Shara says "Captain Bia" and "Keth has
   been there for four decades"; Bia says "My name is Bia". A handle inside a
   spoken line gets READ ALOUD by the generator. Anything between quotes is
   skipped, and so is a name the script deliberately quotes (EXPRESSION: the
   name "Keth" carries weight).

Writes a fixed .md next to the original and prints a full before/after.
"""
import os
import re
import shutil
import sys

SRC = r"C:\Users\Owner\Downloads\TALIA_CREW_EP1_V10_RENUMBERED.md"
BAK = SRC.replace(".md", ".BEFORE_HANDLE_FIX.md")

NAMES = [
    # longest first so "Lady Vor'Shara Vel" wins over "Vor'Shara"
    (r"Lady Vor['\u2019]Shara Vel", "@lady-vor-shara-vel"),
    (r"Vor['\u2019]Shara", "@lady-vor-shara-vel"),
    (r"Talia", "@Talia"),
    (r"Yannah", "@Yannah"),
    (r"Keth", "@Keth"),
    (r"Bia", "@Bia-2"),
]

QUOTED = re.compile(r"[\"\u201c][^\"\u201d]*[\"\u201d]")
DIALOGUE_LINE = re.compile(r"^\**DIALOGUE\s*\(")


def fix_escapes(text: str) -> tuple[str, int]:
    """Strip backslashes that sit INSIDE an @handle token."""
    n = 0

    def _sub(m):
        nonlocal n
        tok = m.group(0)
        clean = tok.replace("\\_", "_").replace("\\*", "*").rstrip("\\")
        if clean != tok:
            n += 1
        return clean

    return re.sub(r"@[A-Za-z][\w\\'\u2019*-]*", _sub, text), n


def fix_names_in_line(line: str) -> tuple[str, list]:
    """Replace plain names OUTSIDE quotes. Returns (new_line, [(old,new)])."""
    if DIALOGUE_LINE.match(line.strip()):
        return line, []                      # a spoken line: never touch it

    # carve the line into quoted / unquoted spans; only edit unquoted spans
    spans, last = [], 0
    for m in QUOTED.finditer(line):
        spans.append((last, m.start(), True))
        spans.append((m.start(), m.end(), False))
        last = m.end()
    spans.append((last, len(line), True))

    changes, out = [], []
    for a, b, editable in spans:
        chunk = line[a:b]
        if editable:
            for pat, handle in NAMES:
                # (?<!@) so an existing handle is not re-prefixed
                # (?<![\w-]) so "Bia" in "@Bia-2" or "Bia-2" is skipped
                rx = re.compile(r"(?<!@)(?<![\w\-'\u2019])" + pat + r"(?![\w\-])")
                for m in rx.finditer(chunk):
                    changes.append((m.group(0), handle))
                chunk = rx.sub(handle, chunk)
        out.append(chunk)
    return "".join(out), changes


def main() -> int:
    text = open(SRC, encoding="utf-8").read()
    if not os.path.exists(BAK):
        shutil.copy2(SRC, BAK)
        print(f"backup -> {BAK}")

    text, esc_n = fix_escapes(text)
    print(f"\n=== 1. backslash escapes stripped from {esc_n} handle tokens ===")

    lines = text.split("\n")
    total = 0
    print("\n=== 2. plain names -> handles (quoted speech skipped) ===")
    for i, line in enumerate(lines):
        new, changes = fix_names_in_line(line)
        if changes:
            lines[i] = new
            total += len(changes)
            what = ", ".join(f"{o} -> {n}" for o, n in changes)
            print(f"\n  L{i+1}  [{what}]")
            print(f"    was: {line.strip()[:135]}")
            print(f"    now: {new.strip()[:135]}")
    text = "\n".join(lines)

    open(SRC, "w", encoding="utf-8").write(text)

    print(f"\n=== totals: {esc_n} escapes, {total} name replacements ===")
    print("\n=== verification ===")
    for label, pat in (
        ("backslash in a handle", r"@[\w'\u2019-]*\\"),
        ("plain Talia", r"(?<!@)\bTalia\b"),
        ("plain Bia", r"(?<!@)(?<![\w-])\bBia\b(?!-2)"),
        ("plain Keth", r"(?<!@)(?<![\w-])\bKeth\b"),
        ("plain Yannah", r"(?<!@)(?<![\w-])\bYannah\b"),
    ):
        hits = re.findall(pat, text)
        print(f"  {label:<24} {len(hits)} left")
    # every survivor must be inside quotes
    survivors = []
    for i, l in enumerate(text.split("\n")):
        for pat, _ in NAMES:
            for m in re.finditer(r"(?<!@)(?<![\w\-'\u2019])" + pat + r"(?![\w\-])", l):
                inside = any(q.start() <= m.start() < q.end() for q in QUOTED.finditer(l))
                if not inside and not DIALOGUE_LINE.match(l.strip()):
                    survivors.append((i + 1, m.group(0), l.strip()[:90]))
    print(f"\n  unquoted survivors (should be 0): {len(survivors)}")
    for s in survivors[:8]:
        print("   ", s)
    print(f"\n  star preserved: {text.count(chr(64) + chr(66) + 'ia' + chr(39) + 's-Pistol*')} "
          f"occurrences of @Bia's-Pistol*")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
