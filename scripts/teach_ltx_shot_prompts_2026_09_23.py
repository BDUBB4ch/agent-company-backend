"""Teach Elliot the LTX shot-prompt doc (verbatim, through ingest.teach; re-run replaces)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import ingest, memory  # noqa: E402
path = os.path.join(os.path.dirname(__file__), "..", "knowledge", "ltx-shot-prompts.md")
text = open(path, encoding="utf-8").read()
print(ingest.teach("MovieDirector", "knowledge", text, title="ltx-shot-prompts"))
with memory.get_db() as c:
    rows = c.execute("select id, content from facts where category='private:MovieDirector' "
                     "and source_name='ltx-shot-prompts.md' and status='active'").fetchall()
assert len(rows) == 1, rows
fact = {"content": rows[0][1], "source_name": "ltx-shot-prompts.md"}
line = memory._skill_use_when(fact, 1200)
print("fact", rows[0][0], len(rows[0][1]), "chars; routing line:", (line or "")[:90])
assert line and "my studio prompt" in line, "routing line not whole"
