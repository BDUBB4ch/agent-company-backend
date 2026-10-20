"""Re-teach Derek's running-omnisend manual from the disk copy.

Run this after editing knowledge/marketing/running-omnisend.md. It exists
because writing fact content through `bash -c "python -c ..."` lets the shell
command-substitute backticks and silently blank tool names out of the text --
it happened to this exact file on 2026-09-01. A script file has no such
problem. Idempotent: ingest.teach replaces the fact with the same title.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))

import ingest  # noqa: E402

path = os.path.join(ROOT, "knowledge", "marketing", "running-omnisend.md")
text = open(path, encoding="utf-8").read()
assert "`read_product`" in text and "`lookup_product`" in text, "tool names missing from doc"
print(ingest.teach("Marketing", "skills", text, title="running-omnisend"))
