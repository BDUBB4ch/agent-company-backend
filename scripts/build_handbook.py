"""Organize the build record into a categorized handbook (Barry, 2026-09-06:
"categorized and organized so when i start building on it again, i won't
need you"). No model calls. Re-runnable.

Reads: CLAUDE.md (global, from the home .claude folder if still present, else
the copy inside BARRYS-AGENTS.md), the project CLAUDE.md, docs/agents-memory/.
Writes: docs/handbook/INDEX.md + one file per topic, each holding every
section of the record that belongs to that topic, newest first, plus
docs/handbook/00-START-HERE.md (written by hand, see START_HERE below).
"""
import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "handbook")
HOME = os.path.expanduser("~")

TOPICS = [  # (file, title, keywords) -- order = tie-break priority
    ("01-running-and-restarting", "Running, restarting, preflight, health",
     ["preflight", "restart", "watchdog", "port 8420", "stack_watchdog", "office_health", "degradation", "backend started", "start everything", "launcher", "running it", "http.server", "hot reload", "venv"]),
    ("02-models-and-backends", "Models, Bonsai, Ollama, VRAM rules",
     ["bonsai", "ollama", "qwen3", "9b", "vram", "num_ctx", "circuit", "tok/s", "prefill", "cache_prompt", "llama-server", "model switch", "overrides", "spill"]),
    ("03-agents-and-roles", "The nine agents, roles, personas, teamwork",
     ["victor", "priya", "ceo", "delegate", "teamwork", "brief", "persona", "personality", "amara", "marcus", "derek", "vivian", "taliyah", "huddle", "hired", "role"]),
    ("04-brain-and-memory", "The brain: facts, skills, recall, pins, standing rules",
     ["always-on", "on-demand", "read_skill", "recall", "pinned", "use when", "brain", "facts", "save_note", "standing rule", "summar", "ingest", "drop/", "teach", "inspect_brain", "brain map", "braingraph"]),
    ("05-sophie-engineering", "Sophie: tools, fixes, watch, updates, capabilities",
     ["sophie", "engineer", "codefix", "propose_code_fix", "watch.py", "read_project_file", "engineer_tools", "update", "run_command", "client-errors", "system_health", "coding"]),
    ("06-elliot-film-and-canon", "Elliot, the Talia Crew, canon, scripts, prompts",
     ["elliot", "canon", "keth", "bia", "tazz", "yannah", "vor'shara", "vorshara", "b dubb", "@b-dubb", "seedance", "higgsfield", "script", "shot", "v9", "v8", "v7", "treatment", "voice", "weapon", "prop", "lora", "character"]),
    ("07-image-and-video-pipeline", "ComfyUI, image and video generation, training",
     ["comfy", "ltx", "sdxl", "qwen-image", "qwen_image", "kontext", "ip-adapter", "ipadapter", "render", "video", "image generation", "checkpoint", "training", "retrain", "pagefile", "gguf", "sulphur", "mystudio", "my studio"]),
    ("08-store-email-and-business", "The store, WooCommerce, Omnisend email, ads, business facts",
     ["omnisend", "woocommerce", "store", "email", "bionova", "merchant center", "plugin", "wordpress", "coupon", "big15", "big10", "ads", "bizwatch", "pricing", "wholesale", "gotcho", "pid", "dispatch", "campaign", "cadence", "klaviyo", "hostinger"]),
    ("09-dashboards-and-decks", "The dashboard and every deck (chamber, neo, talia, crew...)",
     ["deck", "chamber", "neo.html", "neo-", "dashboard", "app.js", "index.html", "deck-core", "roll", "panel", "button", "messenger", "pchat", "homes", "office image", "avatar"]),
    ("10-inner-life-and-social", "Reflections, moods, relationships, group chat, homes, clock",
     ["reflect", "inner life", "mind-", "social", "group chat", "dm", "break room", "breakroom", "mood", "relationship", "hobby", "own time", "clock.py", "work hours", "personal channel", "for barry", "home"]),
    ("11-rules-and-lessons", "Hard rules, Barry's rulings, lessons paid for",
     ["rule", "lesson", "never", "always", "ruling", "do not", "barry:", "supersede", "trap", "footgun", "wrong"]),
]


def read(p):
    return open(p, encoding="utf-8").read() if os.path.isfile(p) else ""


def split_sections(text):
    """Split on '## ' headings and on top-level '- **' bullets of the global file."""
    parts = re.split(r"(?m)^(?=## )", text)
    out = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # the long global file: break its giant bullet lists into one item per bullet
        if len(p) > 20000 and "\n- **" in p:
            head, *bullets = re.split(r"(?m)^(?=- \*\*)", p)
            out.append(head.strip())
            out.extend(b.strip() for b in bullets if b.strip())
        else:
            out.append(p)
    return [s for s in out if len(s) > 80]


def classify(section):
    low = section.lower()
    head = low[:300]
    scores = []
    for i, (fn, title, kws) in enumerate(TOPICS):
        s = 0
        for k in kws:
            c = low.count(k)
            if c:
                s += c + (3 if k in head else 0)
        scores.append((s, -i, fn))
    scores.sort(reverse=True)
    best = scores[0]
    if best[0] == 0:
        return "11-rules-and-lessons"
    return best[2]


def first_line(section):
    m = re.search(r"(?m)^name:\s*(.+)$", section[:400])
    if section.startswith("---") and m:          # memory note frontmatter
        d = re.search(r"(?m)^description:\s*(.+)$", section[:600])
        return (m.group(1).strip() + (" -- " + d.group(1).strip() if d else ""))[:140]
    ln = section.splitlines()[0].strip("#- *").strip()
    return ln[:120]


def build():
    os.makedirs(OUT, exist_ok=True)
    global_txt = read(os.path.join(HOME, ".claude", "CLAUDE.md"))
    if not global_txt:  # Claude removed -- take Part 1 from the merged file
        merged = read(os.path.join(ROOT, "BARRYS-AGENTS.md"))
        m = re.search(r"# PART 1 --.*?\n=+\n\n(.*?)\n=+\n# PART 2", merged, re.S)
        global_txt = m.group(1) if m else ""
    project_txt = read(os.path.join(ROOT, "CLAUDE.md")) or ""
    notes = sorted(glob.glob(os.path.join(ROOT, "docs", "agents-memory", "*.md")))

    buckets = {fn: [] for fn, _, _ in TOPICS}
    for src, text in (("build description", global_txt), ("session record", project_txt)):
        for sec in split_sections(text):
            buckets[classify(sec)].append((src, sec))
    for n in notes:
        if n.endswith("MEMORY.md"):
            continue
        t = read(n)
        buckets[classify(t)].append(("memory note " + os.path.basename(n), t))

    index = ["# BARRY'S AGENTS -- HANDBOOK INDEX", "",
             "Start with 00-START-HERE.md. Each topic file holds every section of the build record",
             "that belongs to that topic (session blocks newest first, then the build description,",
             "then the memory notes). The unsplit full record is ../../BARRYS-AGENTS.md.", "",
             "| file | topic | sections |", "|---|---|---|",
             "| 00-START-HERE.md | How to run it, the rules, where everything is | -- |"]
    for fn, title, _ in TOPICS:
        items = buckets[fn]
        # sessions newest first: session blocks carry dates in the heading
        items.sort(key=lambda it: (0 if it[1].startswith("## SESSION") else 1, -len(it[1]) if not it[1].startswith("## SESSION") else 0))
        items.sort(key=lambda it: (re.search(r"20\d\d-\d\d-\d\d", it[1][:80]) or re.search("", "")).group(0) if it[1].startswith("## SESSION") else "", reverse=True)
        body = [f"# {title}", "", f"{len(items)} sections. Newest sessions first. Source of each section is noted.", ""]
        toc = ["## In this file", ""]
        for i, (src, sec) in enumerate(items, 1):
            toc.append(f"{i}. {first_line(sec)}  *({src})*")
        body += toc + ["", "---", ""]
        for i, (src, sec) in enumerate(items, 1):
            body += [f"<!-- section {i} | source: {src} -->", sec, "", "---", ""]
        open(os.path.join(OUT, fn + ".md"), "w", encoding="utf-8").write("\n".join(body))
        index.append(f"| {fn}.md | {title} | {len(items)} |")
    open(os.path.join(OUT, "INDEX.md"), "w", encoding="utf-8").write("\n".join(index) + "\n")
    print("handbook:", {fn: len(buckets[fn]) for fn, _, _ in TOPICS})


if __name__ == "__main__":
    build()
