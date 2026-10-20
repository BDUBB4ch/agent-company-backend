"""Teach-without-code (2026-08-24, Barry: "one day i may not have you, so i
would need to be able to do these things myself, with a 1 click or drop type
way, no coding").

Two doors, one ingest:
  1. The drop/ folder tree -- drop/<FirstName>/{persona,skills,knowledge}/.
     A background scan (main.py lifespan, every 60s) ingests anything found,
     converts non-text via document_extract, and moves the file to _done/
     (or _failed/ with a .why.txt note). No restart, no chat, no code.
  2. The dashboard Teach box + persona editor (POST /api/agents/{id}/teach,
     GET/PUT /api/agents/{id}/persona-additions) -- type it, save it.

What each kind becomes:
  persona    -> personas/<office_name>.md, appended VERBATIM. Spliced into
                the agent's system prompt right after the authored persona
                (main.py), so it reads as WHO THEY ARE, not a brain fact.
                Always-on weight, so capped -- oversize is refused with a
                pointer to skills/. mtime-cached read: byte-stable between
                edits, so the prompt-cache prefix survives (the 65s->11s
                rule).
  skill      -> on-demand .md fact in private:<office>. A first line
                starting "USE WHEN:" becomes its routing line (existing
                memory._skill_use_when convention).
  knowledge  -> same mechanics as skill -- on-demand .md fact. The split
                exists for Barry's mental model, not the machinery's.

House rules enforced here: words land VERBATIM (no model ever summarizes
on the way in -- the 2026-08-08 canon lesson); replacing an existing title
SUPERSEDES the old fact, never deletes; flat source_names (a folder prefix
collapses titles -- memory._skill_title lesson); no model calls anywhere in
this module, so it can never trip the VRAM eviction chain.
"""

import os
import re
import shutil
from datetime import datetime

import memory
import document_extract

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DROP_ROOT = os.path.join(_ROOT, "drop")
PERSONA_DIR = os.path.join(_ROOT, "personas")

# Folder names are the names Barry actually calls them -- the dashboard's
# first names, not agents.py's role titles.
FOLDER_TO_AGENT = {
    "Victor": "CIO", "Priya": "Operations", "Amara": "BusinessOps",
    "Marcus": "Legal", "Derek": "Marketing", "Vivian": "Creative",
    "Elliot": "MovieDirector", "Sophie": "Engineer", "Taliyah": "Taliyah",
}


def folder_map() -> dict:
    """The teach-drop folders that exist RIGHT NOW: the nine plus every agent
    he has added (2026-09-19, Barry, of a new agent: "i need to be able to drop
    files into her teach thing").

    The map above is a literal of the nine and cannot grow, so a new agent had
    no drop folder and no row in the DESK teach panel -- the one door built for
    exactly this ("i also need a place so i can give them all this type of
    stuff") did not reach the agents most likely to need it.

    A hire's folder is their NAME and its office is their office_name, which
    for a hire is the agent_id. Read live so an agent added a minute ago is
    teachable a minute later, no restart. Lazy import: main imports ingest.
    Falls back to the nine if anything goes wrong -- the built-ins must never
    stop being teachable because a hire lookup failed."""
    out = dict(FOLDER_TO_AGENT)
    try:
        # ⚠️ NEVER `import main` HERE. The backend runs main.py as the entry
        # point, so the live app is sys.modules["__main__"]; importing "main"
        # builds a SECOND copy of the module and re-runs its module level --
        # measured, it took another brain.db backup and populated a parallel
        # CUSTOM_AGENTS that nothing else reads. Look at the running module
        # first and only fall back to a real import (scripts, tests).
        import sys as _sys
        _main = _sys.modules.get("__main__")
        if not hasattr(_main, "CUSTOM_AGENTS"):
            _main = _sys.modules.get("main")
        if not hasattr(_main, "CUSTOM_AGENTS"):
            import main as _main  # a script importing us, not the server
        for aid, rec in (getattr(_main, "CUSTOM_AGENTS", None) or {}).items():
            name = (rec.get("name") or "").strip()
            folder = (name.split()[0] if name else aid).strip()
            if not folder or folder in out:
                continue          # never shadow one of the nine
            out[folder] = rec.get("office_name") or aid
    except Exception as exc:  # noqa: BLE001
        print(f"[teach] could not add hires to the drop map: {exc}")
    return out
KINDS = ("persona", "skills", "knowledge", "personality")

# Persona is always-on weight on EVERY message for that seat. 8K chars of
# additions ~= 2K tokens -- noticeable but sane. Past that, it belongs in
# skills (on-demand) instead; the refusal says so in plain words.
PERSONA_CAP = 15_000   # 8,000 -> 15,000 on 2026-09-13 (Barry: "Amara needs a
                       # bigger cap, 15000 should be good" -- a teach for her
                       # had just 400'd on the 8K line). ~4K tokens on every
                       # message at the limit; Elliot's seat is the tight one.

_persona_cache: dict[str, tuple[float, str]] = {}  # office -> (mtime, text)


def ensure_tree() -> None:
    """Create the whole drop/ tree + personas/ so Barry never has to."""
    os.makedirs(PERSONA_DIR, exist_ok=True)
    for folder in folder_map():          # the nine + every agent he has added
        for kind in KINDS:
            os.makedirs(os.path.join(DROP_ROOT, folder, kind), exist_ok=True)
        os.makedirs(os.path.join(DROP_ROOT, folder, "_done"), exist_ok=True)
        os.makedirs(os.path.join(DROP_ROOT, folder, "_failed"), exist_ok=True)


def _persona_path(office_name: str) -> str:
    return os.path.join(PERSONA_DIR, f"{office_name}.md")


def persona_additions(office_name: str) -> str:
    """The agent's owner-taught persona text, mtime-cached so the per-message
    cost is one os.stat. Empty string when nothing has been taught."""
    path = _persona_path(office_name)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return ""
    cached = _persona_cache.get(office_name)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read().strip()
    except OSError:
        return ""
    _persona_cache[office_name] = (mtime, text)
    return text


PERSONALITY_DIR = os.path.join(_ROOT, "personalities")
_personality_cache: dict[str, tuple[float, str]] = {}


def _personality_path(office_name: str) -> str:
    return os.path.join(PERSONALITY_DIR, f"{office_name}.md")


def personality_of(office_name: str) -> str:
    """WHO THEY ARE OFF THE CLOCK (2026-08-25, Barry: "i dont want their
    personality to be their work persona. this is, personal time").
    A deliberately SEPARATE door from persona_additions: this text is injected
    ONLY into reflection / personal-time prompts (backend/reflect.py), never
    into work chat -- Marcus does not muse about his weekend mid-contract.
    Seeded from Barry's own words verbatim; grows as he edits it."""
    path = _personality_path(office_name)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return ""
    cached = _personality_cache.get(office_name)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read().strip()
    except OSError:
        return ""
    _personality_cache[office_name] = (mtime, text)
    return text


def set_personality(office_name: str, text: str) -> None:
    text = (text or "").strip()
    if len(text) > PERSONA_CAP:
        raise ValueError(
            f"Personality is {len(text):,} chars -- the cap is {PERSONA_CAP:,}. "
            f"Keep the kernel small; the rest of who they are grows in their "
            f"own reflections.")
    os.makedirs(PERSONALITY_DIR, exist_ok=True)
    with open(_personality_path(office_name), "w", encoding="utf-8") as fh:
        fh.write(text + ("\n" if text else ""))
    _personality_cache.pop(office_name, None)


def append_personality(office_name: str, text: str, when: str = "") -> bool:
    """THEY GROW -- append-only (Barry, 2026-08-30: "allow them to add to their
    personality, but not takeaway anything").

    An agent can add something newly true about themselves. It CANNOT remove,
    reword or overwrite a single character of what is already there -- most of
    that text is Barry's own writing about them, and this function physically
    cannot reach it: it only ever concatenates onto the end, after taking a
    backup, and it verifies afterwards that every prior byte survived.

    Their addition is stored VERBATIM under a dated heading that marks it as
    theirs, so his words and their words never blur together.

    Returns False (never raises) if the addition would blow the cap or if the
    file somehow shrank -- growing a personality must never be able to cost
    someone the one they already have.
    """
    text = (text or "").strip()
    # 2026-09-18: was 1200, which silently refused Elliot's own 1.2K answer
    # about his eye for Barry's Decayed World reference. The addition is stored
    # VERBATIM, so a cap that clips is a cap that edits someone's words -- the
    # one thing this function exists not to do. 2000 still bounds it far under
    # PERSONA_CAP; anything longer belongs in a skill, not a personality.
    if not text or len(text) > 2000:
        return False
    existing = personality_of(office_name)
    stamp = when or datetime.now().date().isoformat()
    block = f"\n\n## Added by them, {stamp}\n{text}\n"
    combined = (existing + block).strip()
    if len(combined) > PERSONA_CAP:
        return False
    os.makedirs(PERSONALITY_DIR, exist_ok=True)
    path = _personality_path(office_name)
    if existing:
        try:
            bdir = os.path.join(_ROOT, "data", "personality_backups")
            os.makedirs(bdir, exist_ok=True)
            with open(os.path.join(bdir, f"{office_name}_{stamp}.md"), "w",
                      encoding="utf-8") as fh:
                fh.write(existing)
        except OSError:
            pass
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(combined + "\n")
    _personality_cache.pop(office_name, None)
    # nothing that was there may be gone -- verify, and roll back if it is
    after = personality_of(office_name)
    if existing and existing not in after:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(existing + "\n")
        _personality_cache.pop(office_name, None)
        return False
    return True


# THEY EVOLVE (2026-09-10, Barry: "i want them to be able to evolve or upgrade
# or update their own personality. I need it to work right"). The file has two
# parts: BARRY'S KERNEL (everything above the first of-their-own heading -- his
# words about them, untouchable) and THEIR OWN SECTION (everything from that
# heading down), which is theirs to add to OR rewrite in full. append-only had
# produced three near-identical "Added by them" entries in a row and a
# truncated duplicate; a person who can only append can never change.
_OWN_SECTION_RE = re.compile(r"^##\s*(?:Added by them|In my own words)\b.*$", re.M)
OWN_SECTION_CAP = 1800


def split_personality(office_name: str) -> tuple[str, str]:
    """(barrys_kernel, their_own_section) -- either may be empty."""
    text = personality_of(office_name)
    m = _OWN_SECTION_RE.search(text)
    if not m:
        return text.strip(), ""
    return text[:m.start()].strip(), text[m.start():].strip()


def own_section_of(office_name: str) -> str:
    return split_personality(office_name)[1]


def revise_personality(office_name: str, text: str, when: str = "") -> bool:
    """Replace THEIR OWN SECTION with a new version, in their words. Barry's
    kernel is byte-verified untouched (rolled back if not). Backup first.
    Returns False (never raises) on an empty/oversize revision."""
    text = " ".join(l.strip() for l in (text or "").strip().splitlines() if l.strip())
    text = text.strip()
    if len(text) < 12 or len(text) > OWN_SECTION_CAP:
        return False
    kernel, _old = split_personality(office_name)
    stamp = when or datetime.now().date().isoformat()
    block = f"## In my own words (revised {stamp})\n{text}"
    combined = (kernel + "\n\n" + block).strip() if kernel else block
    if len(combined) > PERSONA_CAP:
        return False
    existing = personality_of(office_name)
    os.makedirs(PERSONALITY_DIR, exist_ok=True)
    path = _personality_path(office_name)
    if existing:
        try:
            bdir = os.path.join(_ROOT, "data", "personality_backups")
            os.makedirs(bdir, exist_ok=True)
            with open(os.path.join(bdir, f"{office_name}_{stamp}_before-revise.md"),
                      "w", encoding="utf-8") as fh:
                fh.write(existing)
        except OSError:
            pass
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(combined + "\n")
    _personality_cache.pop(office_name, None)
    after_kernel, _ = split_personality(office_name)
    if kernel and after_kernel != kernel:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(existing + "\n")
        _personality_cache.pop(office_name, None)
        return False
    return True


def set_persona_additions(office_name: str, text: str) -> None:
    """Full-replace write (the dashboard editor sends the whole box back)."""
    text = (text or "").strip()
    if len(text) > PERSONA_CAP:
        raise ValueError(
            f"Persona additions are {len(text):,} chars -- the cap is "
            f"{PERSONA_CAP:,} because this rides on EVERY message. Move the "
            f"bulk into a skill (on-demand) and keep only the identity here.")
    with open(_persona_path(office_name), "w", encoding="utf-8") as fh:
        fh.write(text + ("\n" if text else ""))
    _persona_cache.pop(office_name, None)


def _slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    return s[:60] or "untitled"


def teach(office_name: str, kind: str, text: str, title: str = "") -> str:
    """One taught item, either door. Returns a human-readable receipt.
    Verbatim always -- this function must never call a model."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Nothing to teach -- the text is empty.")
    kind = {"skill": "skills"}.get(kind, kind)
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")

    if kind == "persona":
        existing = persona_additions(office_name)
        joined = (existing + "\n\n" + text).strip() if existing else text
        set_persona_additions(office_name, joined)  # raises past the cap
        return (f"Added to {office_name}'s persona ({len(text):,} chars). "
                f"It is part of who they are from their next message.")

    if kind == "personality":
        existing = personality_of(office_name)
        joined = (existing + "\n\n" + text).strip() if existing else text
        set_personality(office_name, joined)  # raises past the cap
        return (f"Added to {office_name}'s personality ({len(text):,} chars). "
                f"Personal time only -- it shapes their reflections and "
                f"off-the-clock life, never their work answers.")

    # skills / knowledge -> on-demand .md fact in the agent's private brain.
    if not title:
        title = text.splitlines()[0][:60]
        if title.upper().startswith("USE WHEN"):  # routing line, not a name
            lines = text.splitlines()
            title = (lines[1] if len(lines) > 1 else "untitled")[:60]
    source_name = f"{_slug(title)}.md"  # FLAT -- folder prefixes kill titles
    category = f"private:{office_name}"
    # Same title taught again = replace: supersede the old fact by id, never
    # delete (house rule). add_fact has no upsert; done here at the one spot
    # that needs it.
    with memory.get_db() as conn:
        conn.execute(
            "UPDATE facts SET status = 'superseded' WHERE category = ? "
            "AND source_name = ? AND status = 'active'",
            (category, source_name))
    memory.add_fact(category, text, source_name=source_name, title=title)
    routed = text.upper().startswith("USE WHEN")
    return (f"Taught {office_name} '{title}' ({len(text):,} chars, "
            f"on-demand{', routed by its USE WHEN line' if routed else ''}). "
            f"Replaces any earlier version of the same title.")


def _read_dropped(path: str) -> str:
    """File -> text, converting through document_extract for anything that
    isn't already plain text/markdown."""
    with open(path, "rb") as fh:
        data = fh.read()
    name = os.path.basename(path)
    if name.lower().endswith((".md", ".txt")):
        return data.decode("utf-8", errors="replace")
    return document_extract.extract_text(name, data)


def scan_drop_folders() -> list[str]:
    """One pass over the whole tree. Returns receipts for anything ingested.
    Never raises -- a bad file goes to _failed/ with a .why.txt note and the
    scan continues; teaching must not be able to take the backend down."""
    receipts: list[str] = []
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    # Read live, not from the literal: an agent added since boot is teachable
    # on the very next scan (60s) with no restart.
    for folder, office in folder_map().items():
        agent_dir = os.path.join(DROP_ROOT, folder)
        for kind in KINDS:
            kind_dir = os.path.join(agent_dir, kind)
            if not os.path.isdir(kind_dir):
                continue
            for name in sorted(os.listdir(kind_dir)):
                path = os.path.join(kind_dir, name)
                if not os.path.isfile(path) or name.startswith((".", "~")):
                    continue
                try:
                    text = _read_dropped(path)
                    title = os.path.splitext(name)[0].replace("_", " ")
                    receipt = teach(office, kind, text, title=title)
                    dest = os.path.join(agent_dir, "_done",
                                        f"{stamp}-{kind}-{name}")
                    shutil.move(path, dest)
                    receipts.append(f"{folder}/{kind}/{name}: {receipt}")
                    print(f"[drop] {folder}/{kind}/{name} ingested")
                except Exception as exc:
                    try:
                        dest = os.path.join(agent_dir, "_failed",
                                            f"{stamp}-{kind}-{name}")
                        shutil.move(path, dest)
                        with open(dest + ".why.txt", "w",
                                  encoding="utf-8") as fh:
                            fh.write(f"{datetime.now().isoformat()}\n{exc}\n")
                    except Exception:
                        pass
                    receipts.append(f"{folder}/{kind}/{name}: FAILED -- {exc}")
                    print(f"[drop] {folder}/{kind}/{name} FAILED: {exc}")
    # drop/Characters/<Name>/<view>/ -- pictures for the character engine
    # (2026-09-22). Its own module; a failure there never touches teaching.
    try:
        import char_refs
        receipts += char_refs.scan()
    except Exception as exc:
        print(f"[drop] character pictures scan failed: {exc}")
    return receipts
