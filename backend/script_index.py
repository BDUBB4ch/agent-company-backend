"""Scene-level access to Barry's long production scripts.

WHY THIS EXISTS
---------------
`ep1-wrong-box-script-CANON-v7` is 94,377 chars. Elliot's pinned skills plus
his brain block already spend ~161,000 chars of a ~262,000-char window, so
the script cannot be pinned and cannot be pulled whole: `read_skill` returns
full fact content with no cap, and a 94K tool result pushes the prompt past
the window, where Ollama silently truncates. The observed failure (2026-08-16)
was Elliot inventing the opening scene while claiming to have read three
documents -- he had called no tools at all, because the only tool available
would not have fit.

The script is not really one document. It is 77 rule-separated blocks with a
median size of 1,164 chars -- a database pretending to be a document, the same
shape problem as `product-catalog-full`. This module indexes those blocks so
one scene can be fetched at ~1,500 chars instead of 94,000.

Access is deliberately routed through `memory.get_skill_content`, so an agent
can only reach a script it was already granted. This adds no permission
surface; it only changes how much of an allowed document comes back.
"""

import re

import memory

# The script Elliot is actually working from. Other scripts remain reachable
# by passing `script=` explicitly -- this is only the default.
#
# Barry is still writing this series, so new episodes must become reachable
# WITHOUT a code change. Nothing here hardcodes a filename except this default:
# scripts are discovered structurally (see `list_scripts`), so an EP2 uploaded
# tomorrow is searchable the moment it lands in the brain.
# 2026-09-20: was "ep1-wrong-box-script-CANON-v7" -- a fact that was HARD
# DELETED on 2026-09-14, so every unqualified lookup fell through to an error
# ("No script matching 'ep1-wrong-box-script-CANON-v7'") instead of resolving.
# Points at the live script now. The CANON-title rule below still wins first,
# so a future version Barry titles CANON takes over without a code edit.
# ⚠️ NO ".md" -- `memory._skill_title` strips the suffix, so `list_scripts`
# reports the title as "ep1-production-v10-WIP". A value carrying .md here
# silently never matches and the lookup falls through to the newest-script
# fallback. Caught on install 2026-09-20.
DEFAULT_SCRIPT = "ep1-production-v10-WIP"

# A document counts as a script if it parses into at least this many shot
# blocks. Detecting the shape rather than the filename means Barry can name
# the next episode anything he likes.
_MIN_SHOTS_FOR_SCRIPT = 3

# Blocks are separated by a long horizontal rule. Barry's docs use box-drawing
# dashes; plain hyphens are accepted so a re-export in another editor still
# parses.
_RULE_RE = re.compile(r"^[─-╿\-_=]{20,}\s*$", re.M)

# "SHOT 01 -- THE RUN  |  10 sec  |  MUSIC: ..." / "B-ROLL 03 -- THE FACILITY"
# / "SHOT C5 -- THE ERUPTION". Numbering is NOT contiguous in v7 (SHOT 01-20,
# then C1-C11, then 39-57; B-ROLL 01, 03, 07-12, 16-18, 21, 24), so position
# in the file and printed label are two different things and both are exposed.
_SHOT_RE = re.compile(
    r"^(SHOT|B-ROLL|BROLL)\s+([A-Za-z]?[-\w]*\d+[A-Za-z]?)\s*[—–-]+\s*(.*)$"
)
# "ACT ONE -- COLORADO", "SCENE C -- THE QUARTERS"
_SECTION_RE = re.compile(r"^(ACT|SCENE)\s+([A-Za-z]+)\s*[—–-]+\s*(.*)$")

# A single reply must stay small enough to leave the model room to think.
# A broad query that matches more than this returns an outline of the matches
# instead of their bodies -- never a silent partial dump.
MAX_CHARS = 6000


def _first_line(block: str) -> str:
    for line in block.strip().splitlines():
        if line.strip():
            # Strip markdown decoration ("### **SHOT 01 ...**") -- Barry's
            # 2026-08-21 full-V9 install writes labels inside markdown
            # headers, and script_wip._block_label already tolerates this.
            return line.strip().lstrip("#*[ ").rstrip("]* ")
    return ""


def parse_blocks(text: str) -> list[dict]:
    """Split a script into labelled blocks, tagging each with the ACT/SCENE
    header it falls under so a shot never comes back without its context."""
    blocks: list[dict] = []
    section = ""
    for raw in _RULE_RE.split(text):
        if not raw.strip():
            continue
        header = _first_line(raw)
        kind, label, title = "front", header, ""

        m = _SHOT_RE.match(header)
        if m:
            prefix = "B-ROLL" if m.group(1).upper().startswith("B") else "SHOT"
            kind = "shot"
            label = f"{prefix} {m.group(2).upper()}"
            # Strip the "| 10 sec | MUSIC: ..." tail off the printed title.
            title = m.group(3).split("|")[0].strip()
        else:
            m = _SECTION_RE.match(header)
            if m:
                kind = "section"
                label = f"{m.group(1).upper()} {m.group(2).upper()}"
                title = m.group(3).split("|")[0].strip()
                section = f"{label} -- {title}" if title else label

        blocks.append({
            "position": len(blocks) + 1,
            "kind": kind,
            "label": label,
            "title": title,
            "section": section,
            "content": raw.strip(),
        })
    return blocks


def list_scripts(office_name: str) -> list[dict]:
    """Every script-shaped document this agent can reach, newest facts last.

    Structural detection on purpose: Barry is still writing the series, so
    the next episode must show up here without anyone editing this file.
    """
    found = []
    for fact in memory.get_active_facts_for_agent(office_name):
        if not memory._is_skill_fact(fact):
            continue
        content = fact.get("content") or ""
        # Cheap pre-filter before paying for a full parse on every skill.
        if content.count("SHOT ") < _MIN_SHOTS_FOR_SCRIPT:
            continue
        blocks = parse_blocks(content)
        shots = [b for b in blocks if b["kind"] == "shot"]
        if len(shots) >= _MIN_SHOTS_FOR_SCRIPT:
            found.append({
                "title": memory._skill_title(fact),
                "fact_id": fact.get("id") or 0,
                "shots": len(shots),
                "chars": len(content),
                "blocks": blocks,
            })
    return found


def default_script(office_name: str) -> str:
    """Which script an unqualified read_scene call means.

    Barry names his authoritative drafts with CANON in the title
    (ep1-wrong-box-script-CANON-v7) and a v8 is expected ("elliot and i
    will have to probaly do a version 8", 2026-08-16). A hardcoded default
    would silently keep serving v7 after v8 lands, so: the NEWEST
    CANON-titled script wins, then the hardcoded default, then the newest
    script of any name. Explicit `script=` arguments bypass all of this.
    """
    scripts = list_scripts(office_name)
    canon = [s for s in scripts if "canon" in s["title"].lower()]
    if canon:
        return max(canon, key=lambda s: s["fact_id"])["title"]
    if any(s["title"] == DEFAULT_SCRIPT for s in scripts):
        return DEFAULT_SCRIPT
    if scripts:
        return max(scripts, key=lambda s: s["fact_id"])["title"]
    return DEFAULT_SCRIPT


def _load(office_name: str, script: str) -> tuple[list[dict], str] | tuple[None, str]:
    """Resolve a script through the agent's own skill access. Exact title match
    is preferred so a loose name cannot pull several scripts at once -- the
    substring behaviour that makes read_skill('ep1') return 143K chars."""
    result = memory.get_skill_content(office_name, script)
    if not result.get("found"):
        scripts = [s for s in result.get("available_skills", []) if "script" in s.lower()]
        return None, (
            f"No script matching '{script}'."
            + (f" Scripts you can read: {', '.join(scripts)}." if scripts else "")
        )
    skills = result["skills"]
    exact = [s for s in skills if s["title"].lower() == script.strip().lower()]
    chosen = (exact or skills)[0]
    return parse_blocks(chosen["content"]), chosen["title"]


def _outline(blocks: list[dict], title: str, note: str = "") -> dict:
    lines = []
    for b in blocks:
        if b["kind"] == "section":
            lines.append("")
            lines.append(b["content"].splitlines()[0].strip())
        elif b["kind"] == "shot":
            lines.append(f"  {b['label']} -- {b['title']}")
        else:
            lines.append(f"  [{b['label']}]")
    return {
        "script": title,
        "outline": "\n".join(lines).strip(),
        "note": note or (
            "Ask for any one of these by label (e.g. 'SHOT 12'), by name "
            "(e.g. 'the run'), or by section (e.g. 'act two')."
        ),
    }


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _package(blocks: list[dict], hits: list[dict], title: str) -> dict:
    """Return matched blocks verbatim, or -- if they would blow the budget --
    an outline of the matches plus the first one, so the model is never handed
    a silently cut scene."""
    total = sum(len(b["content"]) for b in hits)
    truncated = total > MAX_CHARS and len(hits) > 1
    shown = [hits[0]] if truncated else hits

    first, last = shown[0], shown[-1]
    prev_b = next((b for b in reversed(blocks)
                   if b["position"] < first["position"] and b["kind"] == "shot"), None)
    next_b = next((b for b in blocks
                   if b["position"] > last["position"] and b["kind"] == "shot"), None)

    out = {
        "script": title,
        "section": first["section"],
        "matched": [b["label"] for b in shown],
        "content": "\n\n".join(b["content"] for b in shown),
        "previous": prev_b["label"] if prev_b else None,
        "next": next_b["label"] if next_b else None,
    }
    if truncated:
        out["note"] = (
            f"{len(hits)} blocks matched ({total:,} chars) -- too much for one "
            f"reply, so only {first['label']} is shown in full. The rest: "
            + ", ".join(b["label"] for b in hits[1:])
            + ". Ask for them one at a time."
        )
    return out


def read_scene(office_name: str, query: str = "", script: str = "") -> dict:
    """One scene from a production script, verbatim.

    query: 'outline' for the shot list, 'first'/'last', a label ('SHOT 12',
    'B-ROLL 07', 'C5'), a section ('act two', 'scene c'), or words from a
    scene's name ('the run').
    """
    blocks, title = _load(office_name, (script or default_script(office_name)).strip())
    if blocks is None:
        return {"found": False, "error": title}

    q = _normalize(query)
    shots = [b for b in blocks if b["kind"] == "shot"]

    if not q or q in ("outline", "list", "index", "contents", "all", "scenes", "shots"):
        return {"found": True, **_outline(blocks, title)}

    if q in ("first", "opening", "first scene", "start", "beginning") and shots:
        # The opening ACT/TITLE CARD block carries the time and place, so it
        # rides along with the first shot rather than being dropped.
        head = [b for b in blocks
                if b["kind"] == "section" and b["position"] < shots[0]["position"]]
        hits = ([head[-1]] if head else []) + [shots[0]]
        return {"found": True, **_package(blocks, hits, title)}

    if q in ("last", "final", "last scene", "ending", "end") and shots:
        return {"found": True, **_package(blocks, [shots[-1]], title)}

    # Label match, e.g. "shot 12", "b roll 07", "c5", or a bare "12".
    # Compared with zero-padding stripped from BOTH sides -- Barry types
    # "shot 3", the blocks are labelled "SHOT 03", and this exact mismatch
    # is what dropped his 2026-08-25 asks through to the body search below,
    # which then served the WRONG block (see the label-shaped guard).
    def _canon(s: str) -> str:
        return re.sub(r"\b0+(\d)", r"\1", s)

    qc = _canon(q)
    label_hits = []
    for b in shots:
        lab = _canon(_normalize(b["label"]))
        if qc == lab or qc == lab.replace("shot ", "").replace("b roll ", ""):
            label_hits.append(b)
    # Since the 2026-09-07 blend the script carries TWO numberings: Betty's
    # ACT ZERO (SHOT 00-05, plain) and V9's shots (SHOT 01A-23A). A bare
    # number means the shot AS IT READS ON THE PAGE, in order: the plain
    # label when one exists (Act Zero), otherwise the lettered V9 twin
    # ("shot 9" -> SHOT 09A, there is no plain 09). When both exist the
    # other one is NAMED in a note, never silently hidden. "shot 1a" typed
    # explicitly resolves exactly as typed. (2026-09-14: Barry is working
    # the script from the top; a first cut of this preferred the lettered
    # block and served THE RUN for "shot 1" -- "thats not the new one".)
    bare = re.fullmatch(r"(?:shot )?(\d+)", qc)
    if bare:
        num = bare.group(1)
        for b in shots:
            lab = _canon(_normalize(b["label"]))
            if re.fullmatch(r"shot " + num + r"[a-z]", lab) and b not in label_hits:
                label_hits.append(b)
    if label_hits:
        lettered = [b for b in label_hits
                    if re.search(r"\d[a-z]$", _normalize(b["label"]))]
        plain = [b for b in label_hits if b not in lettered]
        if lettered and plain and bare:
            packed = _package(blocks, [plain[0]], title)
            packed["note"] = (
                f"Served {plain[0]['label']} ({plain[0]['section']}). "
                f"{lettered[0]['label']} -- {lettered[0]['title']} also "
                f"exists in {lettered[0]['section']}; ask for it by that "
                f"label if that is the one you meant."
            )
            return {"found": True, **packed}
        return {"found": True, **_package(blocks, [label_hits[0]], title)}

    # Section match: return that act/scene's shot list plus its first block,
    # because a whole act is 10+ blocks and well past the budget.
    for b in blocks:
        if b["kind"] == "section" and (q == _normalize(b["label"])
                                       or q == _normalize(b["section"])):
            members = [x for x in blocks if x["section"] == b["section"]
                       and x["kind"] == "shot"]
            listing = "\n".join(f"  {m['label']} -- {m['title']}" for m in members)
            packed = _package(blocks, [b] + members[:1], title)
            packed["note"] = (
                f"{b['section']} contains {len(members)} blocks. Shown: the "
                f"section header and its first block. Full list:\n{listing}"
            )
            return {"found": True, **packed}

    # A label-shaped query that missed both the label loop and the section
    # loop must FAIL HONESTLY, never fall through to the word searches.
    # Proven failure 2026-08-25: "shot 3" (pre-canon fix) fell through and
    # substring-matched "mid shot 35mm" -- a LENS spec -- inside SHOT 01's
    # body, and the verbatim gate served SHOT 01 as a confident, wrong
    # answer with no model call to catch it. "shot 5" matched "tracking
    # shot 50mm" in SHOT 06 the same way. A miss returns the outline so the
    # caller can pick; a wrong hit teaches Barry his director is broken.
    if re.fullmatch(r"(?:shot|b ?roll|scene)s?\s*\d+[a-z]?|\d+[a-z]?|[a-z]", qc):
        return {
            "found": False,
            "error": f"No block in {title} is labelled '{query}'.",
            **_outline(blocks, title, note="Pick one of these instead."),
        }

    # Name match on the scene's own title, then a body search as last
    # resort -- on WORD BOUNDARIES, so a query ending in a digit can never
    # again match inside a lens spec or a timestamp.
    _qre = re.compile(r"\b" + re.escape(q) + r"\b")
    hits = [b for b in shots if _qre.search(_normalize(b["title"]))]
    if not hits:
        hits = [b for b in shots if _qre.search(_normalize(b["content"]))]
    if hits:
        return {"found": True, **_package(blocks, hits, title)}

    return {
        "found": False,
        "error": f"Nothing in {title} matches '{query}'.",
        **_outline(blocks, title, note="Pick one of these instead."),
    }


# How many characters of context to show around a cross-script hit. Enough to
# recognise the moment, deliberately not enough to answer from -- the point is
# to find the label, then fetch that block in full with read_scene.
_SNIPPET = 180
_MAX_HITS = 25


def search_scripts(office_name: str, query: str, script: str = "") -> dict:
    """Find which scene, in which script, contains something.

    This is the half that scales as the series grows: it never loads a script
    into the reply, only labels and one-line snippets, so searching ten
    episodes costs about the same as searching one.
    """
    q = _normalize(query)
    if not q:
        return {"found": False, "error": "Give me something to search for."}

    scripts = list_scripts(office_name)
    if script.strip():
        wanted = script.strip().lower()
        scripts = [s for s in scripts if wanted in s["title"].lower()] or scripts

    if not scripts:
        return {"found": False, "error": "You have no scripts to search."}

    hits, searched = [], []
    for s in scripts:
        searched.append(s["title"])
        for b in s["blocks"]:
            if b["kind"] != "shot":
                continue
            body = _normalize(b["content"])
            pos = body.find(q)
            if pos < 0:
                continue
            start = max(0, pos - _SNIPPET // 3)
            hits.append({
                "script": s["title"],
                "section": b["section"],
                "label": b["label"],
                "title": b["title"],
                "snippet": "..." + body[start:start + _SNIPPET].strip() + "...",
            })

    if not hits:
        return {
            "found": False,
            "error": f"No scene mentions '{query}'.",
            "searched": searched,
        }

    return {
        "found": True,
        "searched": searched,
        "total": len(hits),
        "hits": hits[:_MAX_HITS],
        "note": (
            f"{len(hits)} scene(s) matched"
            + (f", showing the first {_MAX_HITS}" if len(hits) > _MAX_HITS else "")
            + ". These are snippets -- call read_scene with a label "
              "(and the script name) to get the full scene verbatim."
        ),
    }
