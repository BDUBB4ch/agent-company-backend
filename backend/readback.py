"""READ-BACK AFTER EVERY WRITE (2026-09-24, Barry: "yea build the read-back").

The habit Barry liked in Claude: do the thing, then CHECK the result against something real, and
report what you saw. For the office that check lives in code, not in the model: after any tool that
writes something (a file on his desk, a note, a lesson, the business brain, a brief to a teammate, a
picture or art request), the office re-reads what actually landed and puts it into the tool result as
`readback`. The agent then answers from what it SEES, not from what it meant to do.

Pure local reads (files on disk, brain.db rows) -- no model call, no network. Never raises; a check
that cannot run says so ("NOT VERIFIED -- could not check: ..."), which is itself honest.
"""
from __future__ import annotations

import os
import re

import memory

_PLACEHOLDER_RE = re.compile(
    r"<\s*(?:your|insert|add|put)\b[^>]{0,40}>|\[(?:insert|add|your|todo|tbd)[^\]]{0,40}\]|\$X+(?:\.X+)?"
    r"|\blorem ipsum\b|\bTBD\b|\bTeam [ABC]\b|\bPLACEHOLDER\b|\bXX+\b", re.I)
WRITE_TOOLS = {"send_file_to_barry", "save_note", "remember_lesson", "update_business_brain",
               "delegate_to", "change_my_picture", "make_art"}


def _ok(msg: str) -> str:
    return "VERIFIED -- " + msg


def _bad(msg: str) -> str:
    return "NOT VERIFIED -- " + msg + " Tell Barry plainly it did not land; do not say it did."


def _file(result: dict, args: dict) -> str:
    path = result.get("path") or ""
    if not path and result.get("approval_id"):           # write_file returns the desk id, not the path
        import agent_files
        path = agent_files.resolve_download(result["approval_id"]) or ""
    if not path or not os.path.isfile(path):
        return _bad(f"no file found on disk at {path or '(no path returned)'}.")
    size = os.path.getsize(path)
    head = ""
    if path.lower().endswith((".md", ".txt", ".csv", ".json", ".html")):
        with open(path, encoding="utf-8", errors="replace") as fh:
            head = " ".join(fh.read(400).split())[:200]
    body = str(args.get("content") or "")
    holes = sorted({m.group(0) for m in _PLACEHOLDER_RE.finditer(body)})[:5]
    msg = f"{os.path.basename(path)} is on Barry's desk, {size:,} bytes" + (f"; it starts: \"{head}\"" if head else "") + "."
    if holes:
        return _bad(msg[:-1] + f" -- but it contains placeholder text {holes}. A desk file is a deliverable: "
                    "replace every placeholder with real content (or send nothing) before calling it done.")
    if size < 40:
        return _bad(msg[:-1] + " -- which is too small to be a real document.")
    return _ok(msg)


def _note(result: dict, args: dict, office: str) -> str:
    title = (args.get("title") or "").strip()
    slug = "".join(c if c.isalnum() or c == "-" else "-" for c in title.lower().replace(" ", "-"))[:60].strip("-")
    with memory.get_db() as conn:
        row = conn.execute("SELECT id, length(content) FROM facts WHERE category=? AND source_name=? "
                           "ORDER BY id DESC LIMIT 1", (f"private:{office}", f"note-{slug}.md")).fetchone()
    if not row:
        return _bad(f"no saved note titled '{title}' was found in your brain.")
    return _ok(f"note '{title}' is in your brain (fact #{row[0]}, {row[1]:,} chars).")


def _lesson(result: dict, args: dict, office: str) -> str:
    import lessons
    want = " ".join(str(args.get("lesson") or "").split())[:60].lower()
    items = lessons.load(office) or []
    if not want and args.get("about_lesson"):          # a verdict on an existing lesson, no new one
        j = result.get("result") or (result.get("judged") or {}).get("result") or ""
        return _ok(j or f"lesson #{args.get('about_lesson')} judged.")
    if want and any(want[:40] in " ".join(str(it.get("lesson", "")).split()).lower() for it in items):
        return _ok(f"the lesson is on your ledger ({len(items)} lessons kept).")
    return _bad("the lesson is not on your ledger.")


def _brain(result: dict, args: dict) -> str:
    body = " ".join(str(args.get("content") or "").split())[:60]
    with memory.get_db() as conn:
        row = conn.execute("SELECT content FROM facts WHERE source_name='business-brain' ORDER BY id DESC LIMIT 1").fetchone()
    if row and body and body in " ".join((row[0] or "").split()):
        return _ok("the business brain now contains what you wrote.")
    return _bad("what you wrote is not in the business brain.")


def _brief(result: dict) -> str:
    bid = result.get("brief_id")
    with memory.get_db() as conn:
        row = conn.execute("SELECT id, to_office, status FROM briefs WHERE id=?", (bid,)).fetchone() if bid else None
    if not row:
        return _bad(f"brief #{bid} is not on the board.")
    if (row[2] or "").lower() in ("done", "complete", "completed"):
        return _ok(f"brief #{row[0]} on {row[1]}'s board is marked '{row[2]}' -- report what they delivered, not a guess.")
    return _ok(f"brief #{row[0]} is on {row[1]}'s board, status '{row[2]}'. It is handed off, NOT done yet.")


def _queued(result: dict) -> str:
    aid = result.get("approval_id")
    row = memory.get_output_by_id(aid) if aid else None
    if not row:
        return _bad(f"request #{aid} is not in the queue.")
    status = (dict(row).get("status") if hasattr(row, "keys") else None) or "queued"
    return _ok(f"request #{aid} is filed (status '{status}'). Filed is not rendered -- "
               "don't describe a finished picture until you have looked at it.")


def verify(name: str, args, result, office_name: str | None) -> str | None:
    """A one-line read-back for a write tool's result, or None for tools that write nothing."""
    if name not in WRITE_TOOLS or not isinstance(result, dict):
        return None
    if result.get("error") or result.get("saved") is False:
        return None                                   # already an honest failure
    a = args if isinstance(args, dict) else {}
    try:
        if name == "send_file_to_barry":
            return _file(result, a)
        if name == "save_note":
            return _note(result, a, office_name or "")
        if name == "remember_lesson":
            return _lesson(result, a, office_name or "")
        if name == "update_business_brain":
            return _brain(result, a)
        if name == "delegate_to":
            return _brief(result)
        if name in ("change_my_picture", "make_art"):
            return _queued(result)
    except Exception as exc:                          # noqa: BLE001
        return f"NOT VERIFIED -- could not check: {type(exc).__name__}: {str(exc)[:120]}"
    return None
