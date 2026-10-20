"""Throwaway: measure a saved /api/chat shot reply the way Barry sees it."""
import json
import re
import sys

path = sys.argv[1]
d = json.load(open(path, encoding="utf-8"))
r = d.get("reply") or ""

print("reply chars   :", len(r))
print("fell back     :", d.get("bonsai_fell_back"))
print("image_prompt  :", len(d.get("image_prompt") or ""), "chars")

fields = {
    "CAMERA": r"CAMERA:\s*(.+?)(?=\n[A-Z][A-Z &]{2,}:|\n```|\Z)",
    "ENVIRONMENT & LIGHTING": r"ENVIRONMENT & LIGHTING:\s*(.+?)(?=\n[A-Z][A-Z &]{2,}:|\n```|\Z)",
    "EXPRESSION": r"EXPRESSION:\s*(.+?)(?=\n[A-Z][A-Z &]{2,}:|\n```|\Z)",
    "NEG": r"NEG:\s*(.+?)(?=\n[A-Z][A-Z &]{2,}:|\n```|\Z)",
}
for name, pat in fields.items():
    m = re.search(pat, r, re.S)
    print(f"{name:24}: {len(m.group(1).strip()) if m else 0}")

fence = re.search(r"```image\s*(.*?)```", r, re.S)
print("fence                   :", len(fence.group(1).strip()) if fence else 0)

print("\n-- voice id lines --")
for m in re.finditer(r"(@[\w'\-]+)\s+speaks in voice\s+([0-9a-f-]+)\s*\(([^)]+)\)", r, re.I):
    print(" ", m.group(1), "->", m.group(2)[:8], "(" + m.group(3) + ")")

print("\n-- office notes --")
for m in re.finditer(r"\(Office [^)]{0,200}", r):
    print(" ", m.group(0)[:150])
