"""Throwaway: dump the literal prompt text of Elliot's shot-ask directive.

Locates the directive by its OPENING ANCHOR rather than hardcoded line numbers
-- the first version used lines 5125-5552 and silently measured the wrong
region the moment an edit shifted the file.
"""
import re
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
lines = open(os.path.join(ROOT, "backend", "main.py"), encoding="utf-8").read().split("\n")

start = next(i for i, l in enumerate(lines) if "[SHOT ASK. THE JOB, FROM BARRY" in l)
# the block ends at the closing paren of this `_outgoing += (` at the same indent
end = next(i for i in range(start, len(lines)) if re.match(r"^\s{12}\)\s*$", lines[i]))

LIT = re.compile(r'"((?:[^"\\]|\\.)*)"')
out = []
for line in lines[start:end + 1]:
    if line.strip().startswith("#"):
        continue
    out.extend(LIT.findall(line))

text = "".join(out)
dest = os.path.join(ROOT, "data", "_shot_directive_dump.txt")
with open(dest, "w", encoding="utf-8") as fh:
    fh.write(text)
print(f"directive lines {start + 1}-{end + 1}")
print(f"{len(text)} chars  ~{round(len(text) / 4)} tokens  -> {dest}")
