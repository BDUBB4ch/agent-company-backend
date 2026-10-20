"""Check the returned V10 .md against the five problems handed to Sintra."""
import collections
import os
import re
import sys

MD = r"C:\Users\Owner\Downloads\TALIA_CREW_EP1_V10_RENUMBERED.md"
text = open(MD, encoding="utf-8").read()

FAILS = []


def check(label, ok, detail=""):
    print(("[OK  ] " if ok else "[FAIL] ") + label + (f"  {detail}" if detail else ""))
    if not ok:
        FAILS.append(label)


print(f"file: {len(text):,} chars, U+FFFD {text.count(chr(0xFFFD))}")
print()

print("=== structure (must still be intact) ===")
HEAD = re.compile(r"^#*\s*\**\s*((?:SHOT|B-ROLL)\s+[0-9A-Za-z]+)\b", re.M)
labels = [m.group(1).strip().upper() for m in HEAD.finditer(text)]
dupes = sorted({l for l in labels if labels.count(l) > 1})
check("32 blocks", len(labels) == 32, f"{len(labels)}")
check("no duplicate shot labels", not dupes, str(dupes))
check("no lettered second track",
      not re.search(r"^#*\s*\**\s*(?:SHOT|B-ROLL)\s+\d+[A-Z]\b", text, re.M))

print()
print("=== PROBLEM 1 -- bare DIALOGUE: ===")
bare = re.findall(r"^\**DIALOGUE\s*:", text, re.M)
check("zero unattributed dialogue lines", not bare, f"{len(bare)} left")

print()
print("=== PROBLEM 2 -- speaker labels must be @handles ===")
names = collections.Counter(n.strip() for n in
                            re.findall(r"^\**DIALOGUE\s*\(([^)]+)\)\s*:", text, re.M))
plain = {n: c for n, c in names.items() if not n.startswith("@")}
for n, c in names.most_common():
    print(f"    {c:>3}  {'@' if n.startswith('@') else 'PLAIN '} {n}")
check("every speaker label is an @handle", not plain, str(sorted(plain)))
check("no speaker called 'Barry'", not any("barry" in n.lower() for n in names))

print()
print("=== PROBLEM 3 -- one speaker format ===")
odd = [m.group(0).strip() for m in
       re.finditer(r"^\**[A-Z][A-Za-z' \-]{2,20}\s+whispers\s*:.*$", text, re.M)]
odd += [m.group(0).strip() for m in
        re.finditer(r"^\**([A-Z][A-Z' \-]{2,20})\s*:\s*[\"\u201c]", text, re.M)
        if m.group(1) not in ("DIALOGUE", "CAMERA", "NEG", "VO", "SFX", "MUSIC")]
check("no alternate speaker formats", not odd, str(odd[:3]))

print()
print("=== PROBLEM 4 -- markdown escape artifacts ===")
check("no backslash escapes", text.count("\\_") == 0, f"{text.count(chr(92) + '_')} left")
check("@loc_hidden-black-site spelled clean",
      "@loc_hidden-black-site" in text or "black site" in text.lower())

print()
print("=== PROBLEM 5 -- plain names in the prose ===")
PROSE = {
    "Talia": (r"(?<!@)\bTalia\b", "@Talia"),
    "Bia": (r"(?<!@)(?<!-)\bBia\b(?!-2)", "@Bia-2"),
    "Keth": (r"(?<!@)\bKeth\b", "@Keth"),
    "Yannah": (r"(?<!@)\bYannah\b", "@Yannah"),
    "Vor'Shara": (r"(?<!@)\bVor'Shara\b", "@lady-vor-shara-vel"),
}
for label, (pat, to) in PROSE.items():
    n = len(re.findall(pat, text))
    check(f"no plain '{label}'", n == 0, f"{n} left -> should be {to}")

print()
print("=== handles + weapons now in use ===")
for h, n in collections.Counter(re.findall(r"@[A-Za-z][\w\\''-]*", text)).most_common(24):
    print(f"    {n:>4}  {h}")

print()
print("=== voice ids (all six must survive) ===")
ROSTER = {
    "@b-dubb": "9b162037-e549-4065-9562-ebac293ee72a",
    "@Bia-2": "f32c8f51-449e-4ddf-bdf7-1527e11df917",
    "@Yannah": "032386ec-491b-5bdc-81ac-49e9a6a2c89d",
    "@Tazz": "3811e986-0891-47cf-a1f5-78a1d62a547a",
    "@Keth": "6b528d43-c056-4a2f-9d82-1591a7ba13b0",
    "@lady-vor-shara-vel": "d081b915-6623-4a44-bacf-80d0f1c90a03",
}
for h, v in ROSTER.items():
    check(f"{h} voice id present", v in text)

print()
print(f"DIALOGUE lines total: {len(re.findall(r'DIALOGUE', text))}")
print(f"voice-id lines      : {len(re.findall(r'speaks in voice', text))}")
print()
print("ALL OK -- safe to install" if not FAILS
      else f"{len(FAILS)} PROBLEM(S): " + "; ".join(FAILS))
sys.exit(1 if FAILS else 0)
