"""The LIVING V9 production script -- Elliot's working memory of the story.

Built 2026-08-20 on Barry's instruction: "he needs to just know the script. it
should be who he is -- this story, the characters, everything. it should be
something he knows and updates all the time we work on it, whether we delete or
rewrite, Elliot needs to be able to keep up."

TWO PIECES, two speeds -- the same always-on/on-demand split the whole brain uses:

1. THE WIP SCRIPT (`ep1-production-v9A.1-WIP.md`, on-demand). The V9 production
   script as it currently stands, one fact, V7 block format. Because it uses the
   V7 separators, `script_index` discovers it STRUCTURALLY once it holds 3+ shot
   blocks -- from that moment read_scene / search_script / the verbatim gate all
   serve the LIVE version with zero extra wiring. Elliot writes to it through the
   save_script_block / delete_script_block tools as Barry approves or cuts.

2. THE LEDGER (`ep1-v9A.1-live-state`, source_name deliberately WITHOUT .md, so it
   rides ALWAYS-ON in Elliot's prompt). A compact regenerated outline: every
   block label + name in order, counts, and the working rules. This is the "he
   just knows the story" piece -- the shape of the whole episode is in front of
   him on every message, and any block's full text is one read_scene away.

WHY NOT PIN THE WHOLE SCRIPT: the finished script will be ~90K chars against a
160K pin budget already 127K deep -- and the full story corpus (305K) exceeds
his entire context window. Structure always-on + instant scene fetch is the
working equivalent of "knows it all", and it is the honest version.

SAFETY: every mutation backs up the full previous WIP to
data/script_wip_backups/ first, and deletes archive the removed block inside the
backup file. Nothing here touches V7 or any other authored document -- this
module can only write to the ONE WIP fact and its ledger.
"""
from __future__ import annotations

import datetime
import pathlib
import re

import memory

OFFICE = "MovieDirector"
# ⚡ V10 ON 2026-09-20. Barry brought back a renumbered script from Sintra:
# "New and fixed. everything is better. read it and give to elliot as canon.
# delete old shit, even from his mind or wherever."
# WHAT V10 FIXES, and it was a real defect in the document, not in Elliot:
# V9A.1 carried TWO numbering runs in one file -- his Act Zero 00-05 alongside
# Betty's 01A-23A -- so there were two SHOT 03s and two SHOT 04s. Asking for
# "shot 3" served CREW ASSEMBLY when he meant THE CALL, and it read as Elliot
# handing back old material. V10 is a single run: B-ROLL 00-02 + SHOT 00-28,
# 32 blocks, ZERO duplicate labels, ZERO lettered second track (verified on
# install). V9A.1 was HARD DELETED, per his standing 2026-09-14 rule.
WIP_SOURCE = "ep1-production-v10-WIP.md"
LEDGER_SOURCE = "ep1-v10-live-state"
_REPO = pathlib.Path(__file__).resolve().parent.parent
_BACKUP_DIR = _REPO / "data" / "script_wip_backups"

_SEP = "─" * 110  # the V7 separator line, so script_index parses the WIP

_LABEL_RE = re.compile(
    r"^(TITLE CARD|SHOT\s+[A-Z]?\d+[A-Z]?|B[-\s]?ROLL\s+\d+|ACT\s+\w+|SCENE\s+[A-Z]\b)",
    re.IGNORECASE)

_WIP_HEADER = (
    "TALIA CREW SERIES\n"
    'EPISODE 1 -- "WRONG BOX"\n'
    "Production Script V9A.1 -- WORK IN PROGRESS (living document)\n"
    "Created by: Barry White (B DUBB)  |  B DUBB Grows LLC\n"
    "This is the LIVE V9 production script, built pass by pass with Barry from\n"
    "his V9 treatment. Blocks appear here when Barry approves them. Character\n"
    "anchors: the CURRENT canon (barry-character-canon), never the treatment's.\n"
)


def _norm_label(label: str) -> str:
    """Normalise a block label for matching: SHOT 3 == SHOT 03 == shot 3."""
    s = re.sub(r"\s+", " ", label.strip().upper()).replace("B ROLL", "B-ROLL")
    m = re.match(r"^(SHOT|B-ROLL)\s+([A-Z]?)0*(\d+)([A-Z]?)$", s)
    if m:
        return f"{m.group(1)} {m.group(2)}{int(m.group(3))}{m.group(4)}"
    return s


def _get_wip_fact() -> dict | None:
    for f in memory.get_active_facts_for_agent(OFFICE):
        if f.get("source_name") == WIP_SOURCE:
            return f
    return None


def _split_blocks(content: str) -> tuple[str, list[str]]:
    """(header, [block texts]) -- blocks are separated by the V7 rule lines."""
    parts = [p.strip("\n") for p in content.split(_SEP)]
    parts = [p for p in parts if p.strip()]
    if parts and not _LABEL_RE.match(parts[0].strip().splitlines()[0].strip()):
        return parts[0], parts[1:]
    return _WIP_HEADER, parts


def _block_label(block_text: str) -> str:
    for line in block_text.splitlines():
        # Strip decoration the model wraps labels in -- measured 2026-08-21:
        # Elliot saved "[SHOT 01 -- THE RUN]" and the bracket made the label
        # unparseable, leaving an unlabelled block that could never be
        # replaced or deleted by name.
        line = line.strip().lstrip("[#* ").rstrip("]# ")
        if not line:
            continue
        m = _LABEL_RE.match(line)
        return _norm_label(m.group(1)) if m else ""
    return ""


def _write_wip(header: str, blocks: list[str]) -> None:
    content = header.rstrip("\n") + "\n"
    for b in blocks:
        content += f"{_SEP}\n{b.strip()}\n"
    fact = _get_wip_fact()
    if fact:
        with memory.get_db() as conn:
            conn.execute("UPDATE facts SET content = ? WHERE id = ?",
                         (content, fact["id"]))
    else:
        memory.add_fact(category=f"private:{OFFICE}", content=content,
                        source_name=WIP_SOURCE,
                        title="EP1 V9A.1 production script -- WORK IN PROGRESS")
    _regenerate_ledger(blocks)


def _backup(action: str, label: str) -> None:
    # Barry, 2026-09-14: "Stop keeping shit as a back up." No copies of the
    # script are written anywhere; the WIP fact is the only script.
    return


def _regenerate_ledger(blocks: list[str]) -> None:
    """The always-on outline: rebuilt on every change, small on purpose."""
    lines = []
    for b in blocks:
        first = next((ln.strip() for ln in b.splitlines() if ln.strip()), "")
        lines.append(f"  {first[:88]}")
    shots = sum(1 for b in blocks if _block_label(b).startswith(("SHOT", "B-ROLL")))
    body = (
        "EP1 V9A.1 PRODUCTION SCRIPT -- LIVE STATE (this updates every time a "
        "block is saved or cut; it is always in front of you)\n"
        f"Blocks so far: {len(blocks)} ({shots} shots/B-rolls). Order below is "
        "script order. Full text of any block: read_scene on the WIP script "
        "('ep1-production-v9A.1-WIP').\n\n"
        + ("\n".join(lines) if lines else
           "  (empty -- no blocks approved yet; the V9 treatment chunks hold "
           "the material to convert)")
        + "\n\nHOW THIS DOCUMENT STAYS ALIVE -- your job, every working pass:\n"
        "* When Barry APPROVES a block you wrote, save it with "
        "save_script_block (label + the FULL block text, every field). Approved "
        "means he said yes -- never save unapproved drafts.\n"
        "* When Barry says CUT / DELETE a block, remove it with "
        "delete_script_block. It is archived, never lost.\n"
        "* When Barry REWRITES, save the new version under the same label -- "
        "it replaces in place.\n"
        "* This ledger is your knowledge of where the episode stands. Trust "
        "it over your memory of past conversations."
    )
    with memory.get_db() as conn:
        row = conn.execute(
            "SELECT id FROM facts WHERE source_name = ? AND status = 'active' "
            "AND category = ?", (LEDGER_SOURCE, f"private:{OFFICE}")).fetchone()
        if row:
            conn.execute("UPDATE facts SET content = ? WHERE id = ?",
                         (body, row["id"]))
            return
    memory.add_fact(category=f"private:{OFFICE}", content=body,
                    source_name=LEDGER_SOURCE,
                    title="EP1 V9A.1 production script -- live state")


def save_block(label: str, text: str) -> dict:
    """Upsert one approved block into the WIP script. Returned, never raised."""
    label = (label or "").strip()
    text = (text or "").strip()
    if not label or not text:
        return {"ok": False, "error": "save_script_block needs a label and the full block text."}
    if len(text) > 6000:
        return {"ok": False, "error": "That block is over 6,000 chars -- one block at a time."}
    norm = _norm_label(label)
    if not _LABEL_RE.match(norm):
        return {"ok": False, "error": f"'{label}' is not a block label (SHOT N / B-ROLL N / TITLE CARD / SCENE X)."}
    text_label = _block_label(text)
    if not text_label:
        return {"ok": False,
                "error": "The block text must START with its label line "
                         "(e.g. 'SHOT 01 -- THE RUN | 10 sec | MUSIC: ...') -- "
                         "no brackets, no markdown around it."}
    if text_label != norm:
        return {"ok": False,
                "error": f"The text starts with '{text_label}' but you said '{norm}' -- "
                         "they must match, so the wrong block can't be overwritten."}

    fact = _get_wip_fact()
    header, blocks = _split_blocks(fact["content"]) if fact else (_WIP_HEADER, [])
    _backup("save", norm)
    for i, b in enumerate(blocks):
        if _block_label(b) == norm:
            blocks[i] = text
            _write_wip(header, blocks)
            return {"ok": True, "action": "replaced", "label": norm,
                    "blocks_total": len(blocks)}
    blocks.append(text)
    _write_wip(header, blocks)
    return {"ok": True, "action": "added", "label": norm,
            "blocks_total": len(blocks)}


def delete_block(label: str) -> dict:
    """Remove one block (archived in the backup, never truly lost)."""
    norm = _norm_label((label or "").strip())
    fact = _get_wip_fact()
    if not fact:
        return {"ok": False, "error": "The WIP script is empty -- nothing to delete."}
    header, blocks = _split_blocks(fact["content"])
    keep = [b for b in blocks if _block_label(b) != norm]
    if len(keep) == len(blocks):
        have = ", ".join(_block_label(b) for b in blocks) or "(none)"
        return {"ok": False, "error": f"No block labelled '{norm}'. Blocks: {have}"}
    _backup("delete", norm)
    _write_wip(header, keep)
    return {"ok": True, "action": "deleted", "label": norm, "blocks_total": len(keep)}
