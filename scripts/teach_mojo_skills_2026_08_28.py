"""Teach Sophie the official Modular Mojo skills (Barry, 2026-08-28: found
modular/skills on GitHub -- "anthropic approved plugins for you to learn and
create a skill for my agents").

Source: tools/modular-skills/ (github.com/modular/skills, cloned same day).
mojo-syntax is Modular's own correction layer for AI models' stale pretrained
Mojo knowledge -- exactly what Sophie's models have. It is 23.9K, over the 20K
RECALL_BUDGET, so it is split into two routed parts at a section boundary.
The interop and GPU skills are taught whole (recall names them if oversize;
read_skill serves them in full). Frontmatter and editorial comments stripped;
content otherwise VERBATIM -- Modular's engineers wrote it terse on purpose.

Re-runnable: teach upserts by title.
"""
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.join(os.path.dirname(__file__), "..")
SKILLS = os.path.join(ROOT, "tools", "modular-skills")
API = "http://127.0.0.1:8420/api/agents/engineer/teach"


def load_skill(name):
    text = open(os.path.join(SKILLS, name, "SKILL.md"), encoding="utf-8").read()
    text = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)        # frontmatter
    text = re.sub(r"<!--.*?-->\n?", "", text, flags=re.S)            # editorial comments
    return text.strip()


def teach(title, text):
    body = json.dumps({"kind": "knowledge", "title": title, "text": text}).encode("utf-8")
    req = urllib.request.Request(API, data=body,
                                 headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))
    print(title, "->", r.get("receipt", r))


syntax = load_skill("mojo-syntax")
SPLIT = "## Memory and pointer types"
assert SPLIT in syntax, "split anchor missing -- upstream skill changed, re-check"
part1, part2 = syntax.split(SPLIT, 1)
part2 = SPLIT + part2

teach(
    "mojo-syntax-corrections",
    "USE WHEN: writing, reviewing, translating, or fixing ANY Mojo code. Your "
    "training data contains OBSOLETE Mojo syntax -- this official Modular "
    "correction layer overrides it. Part 1: removed syntax, var, def, raises, "
    "comptime, structs, imports, Writable, iterators.\n\n"
    "(Official skill from github.com/modular/skills, verbatim. Part 2 is "
    "mojo-syntax-advanced. NOTE: written for LATEST Mojo; stable 1.0 may "
    "differ slightly -- when a build fails, trust the compiler.)\n\n" + part1.strip(),
)
teach(
    "mojo-syntax-advanced",
    "USE WHEN: writing Mojo involving pointers, origins, SIMD, closures, "
    "strings, testing, error handling, or collection literals. Part 2 of the "
    "official Modular syntax correction layer (part 1: "
    "mojo-syntax-corrections). Overrides your pretrained Mojo knowledge.\n\n"
    + part2.strip(),
)
teach(
    "mojo-python-interop",
    "USE WHEN: making Mojo call Python, Python call Mojo, building Python "
    "extension modules in Mojo, or bridging Python libraries with Mojo code. "
    "Official Modular skill, verbatim.\n\n" + load_skill("mojo-python-interop"),
)
teach(
    "mojo-gpu-fundamentals",
    "USE WHEN: writing GPU kernels or GPU code in Mojo (NVIDIA, AMD, Apple "
    "silicon). Official Modular skill, verbatim. REALITY CHECK for this "
    "machine: Barry's RX 9070 XT (RDNA4) is community-tier in MAX and Mojo "
    "is WSL-only on Windows -- treat local GPU Mojo as experimental (see "
    "mojo-language).\n\n" + load_skill("mojo-gpu-fundamentals"),
)
print("done.")
