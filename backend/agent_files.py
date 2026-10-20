"""FILES: agents can read files Barry gives them, write real documents, and
hand them to him as a download.

Barry, 2026-09-06: "Make them able to read, write and send me files."

WHAT WAS ACTUALLY MISSING, measured before building. The office could already
turn a file INTO brain knowledge (the drop/ teach tree, the upload endpoint)
and Sophie could read/write SOURCE CODE (read_project_file, codefix.propose_write).
What no agent could do was produce a DOCUMENT for Barry. The only file-serving
endpoint in the build (/api/outputs/{id}/file) served rendered media only, so
every deliverable -- a script, a draft, a plan -- ended its life as text in a
chat window that he had to select and copy.

THREE DOORS, and they are deliberately separate:

  1. READ    drop/_files/  -- he drops a file here, any agent can read it.
             Deliberately NOT the teach tree: teaching writes a permanent fact
             into a brain, and "read this contract and tell me what you think"
             is not a thing anyone wants memorised forever. Read-only; nothing
             here is ever modified or moved by an agent.

  2. WRITE   data/agent_files/<office>/ -- one folder per agent, their own work.
             Sandboxed by construction: the filename is sanitised down to a
             bare name (no separators, no traversal, allowlisted extension) and
             joined to THAT agent's folder, so there is no argument any model
             can pass that writes outside its own shelf. This is the whole
             reason it does not reuse codefix.propose_write, which can touch
             real source and is gated accordingly.

  3. SEND    The file is registered as an output row (the same table and the
             same /api/outputs/{id}/file endpoint that has served Vivian's
             images since July), so it shows up in his Out box with a download
             button and needs no new plumbing to reach him.

NOT APPROVAL-GATED, on purpose. The standing rule is that nothing OUTBOUND
moves without his click -- an email, a post, a send. A file written to his own
machine, for his own eyes, is the same category as a chat reply: it is the
agent answering him. Gating it would mean he has to approve being given the
thing he just asked for. Nothing here can reach the internet.

THE SCRIPT CASE IS SPECIAL AND IS WHY export_script EXISTS. Elliot's episode is
~94,000 characters living in the database. A model reply is capped at 4,096
tokens, so "give me the whole episode as a file" is physically impossible if
the agent has to retype it -- he would silently hand over a fragment. So the
export pulls the assembled document straight from the DB and writes it byte
for byte, no model call in the path. Same principle as the verbatim script gate
and as dispatch's approved-bytes rule: when the exact text already exists,
never let a model re-type it.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import shutil

import config
import memory

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Where agents write. One folder per agent, created on demand.
FILES_ROOT = os.path.join(config.DATA_DIR, "agent_files")

# Where Barry drops files FOR them to read. Sits inside drop/ so it is next to
# the TEACH DROP shortcut he already uses, but the underscore name is not in
# ingest.FOLDER_TO_AGENT, and scan_drop_folders() iterates that map rather than
# listing the directory -- so the teach scanner cannot see this folder and will
# never ingest, move, or consume anything in it. Verified against ingest.py.
INBOX_ROOT = os.path.join(_ROOT, "drop", "_files")

# What an agent is allowed to write. Deliberately documents and data only --
# no .py, .bat, .ps1, .exe, .dll, .lnk. An agent that could write an executable
# into a folder Barry opens is a different and much worse feature than this one.
WRITABLE_EXTS = ("md", "txt", "csv", "json", "html", "docx", "xlsx")

# Generous but finite. Elliot's whole episode is ~94K, so this holds the
# largest real document in the build with room to spare.
MAX_CHARS = 500_000

# One agent's own shelf. Past this, older files are their problem to clean up,
# but the count is reported so it never silently fills the disk.
MAX_FILES_PER_AGENT = 200


def ensure_tree() -> None:
    """Create both folders + a README in the inbox, so Barry never has to."""
    os.makedirs(FILES_ROOT, exist_ok=True)
    os.makedirs(INBOX_ROOT, exist_ok=True)
    readme = os.path.join(INBOX_ROOT, "_READ ME.txt")
    if not os.path.isfile(readme):
        try:
            with open(readme, "w", encoding="utf-8") as fh:
                fh.write(
                    "DROP FILES HERE FOR YOUR AGENTS TO READ.\n"
                    "\n"
                    "Anything in this folder can be read by any agent when you ask them\n"
                    "to -- 'read the lease in my files and tell me what's wrong with it'.\n"
                    "\n"
                    "This is NOT the teach folder. Nothing here goes into anyone's\n"
                    "permanent memory, nothing gets moved, and nothing is deleted.\n"
                    "It is a shelf they can look at.\n"
                    "\n"
                    "Works with: pdf, docx, xlsx, pptx, csv, html, rtf, txt, md, zip,\n"
                    "and images/video (they get described).\n"
                    "\n"
                    "Files they make FOR you land in data\\agent_files\\ and show up\n"
                    "in the DESK panel on your dashboard with a download button.\n")
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Filename safety
# ---------------------------------------------------------------------------

def _safe_name(filename: str, default_ext: str = "md") -> tuple[str, str]:
    """A model-supplied filename reduced to a bare safe name + its extension.

    Everything that could escape the agent's own folder is removed rather than
    rejected, because a refusal here costs a whole generation: the model would
    have to be asked again, and it does not reliably learn from one error
    string. Path separators, '..', drive letters and control characters cannot
    survive this, so the join in _agent_dir() is safe by construction.
    """
    name = (filename or "").strip().replace("\\", "/")
    name = name.split("/")[-1]                      # kills any path, incl. C:/x
    name = name.split(":")[-1]                      # kills a bare drive prefix
    name = re.sub(r"[^A-Za-z0-9 ._-]", "", name)    # kills control chars + junk
    name = re.sub(r"\.{2,}", ".", name).strip(" .") # kills '..' traversal
    if not name:
        name = "document"

    if "." in name:
        stem, ext = name.rsplit(".", 1)
        ext = ext.lower()
    else:
        stem, ext = name, default_ext
    if ext not in WRITABLE_EXTS:
        # An agent asking for .pdf or .py gets a document it can actually
        # write, with the reason reported back, rather than a hard failure.
        ext = default_ext
    stem = (stem or "document")[:80].strip(" .-_") or "document"
    return f"{stem}.{ext}", ext


def _agent_dir(office_name: str) -> str:
    safe_office = re.sub(r"[^A-Za-z0-9_-]", "", (office_name or "shared"))[:40] or "shared"
    path = os.path.join(FILES_ROOT, safe_office)
    os.makedirs(path, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def _write_docx(path: str, text: str, title: str = "") -> None:
    """Markdown-ish text -> a real Word document.

    Deliberately shallow: headings, bullets, paragraphs. Anything cleverer
    (tables, styles) would start silently reshaping an agent's words, and the
    words are the deliverable.
    """
    from docx import Document  # verified present in the venv 2026-09-06

    doc = Document()
    if title:
        doc.add_heading(title, level=0)
    for raw in text.split("\n"):
        line = raw.rstrip()
        if not line.strip():
            doc.add_paragraph("")
            continue
        stripped = line.lstrip()
        if stripped.startswith("#"):
            hashes = len(stripped) - len(stripped.lstrip("#"))
            doc.add_heading(stripped.lstrip("#").strip(), level=min(max(hashes, 1), 4))
        elif stripped.startswith(("- ", "* ")):
            doc.add_paragraph(stripped[2:], style="List Bullet")
        else:
            doc.add_paragraph(line)
    doc.save(path)


def _write_xlsx(path: str, text: str) -> None:
    """CSV-shaped text -> a spreadsheet. Anything that is not comma-separated
    lands in column A rather than being dropped."""
    import csv as _csv
    import io

    from openpyxl import Workbook  # verified present in the venv 2026-09-06

    wb = Workbook()
    ws = wb.active
    for row in _csv.reader(io.StringIO(text)):
        ws.append(row if row else [""])
    wb.save(path)


def write_file(office_name: str, filename: str, content: str,
               what_it_is: str = "", agent_id: str = "") -> dict:
    """Write one document for Barry and register it so he can download it.

    Returns a plain dict either way -- never raises. A tool that throws costs
    the agent its whole turn, and "I could not write that file" is a useful
    answer where a stack trace is not.
    """
    ensure_tree()
    content = content if isinstance(content, str) else str(content)
    if not content.strip():
        return {"error": "There is nothing in the file -- write the content first."}

    truncated = False
    if len(content) > MAX_CHARS:
        content = content[:MAX_CHARS]
        truncated = True

    requested = (filename or "").strip()
    name, ext = _safe_name(requested, default_ext="md")
    ext_changed = bool(requested) and not requested.lower().strip().endswith(ext)

    folder = _agent_dir(office_name)
    path = os.path.join(folder, name)

    # Never silently overwrite yesterday's work: same name gets a counter.
    if os.path.exists(path):
        stem = name[: -(len(ext) + 1)]
        for n in range(2, 100):
            candidate = os.path.join(folder, f"{stem}-{n}.{ext}")
            if not os.path.exists(candidate):
                path, name = candidate, f"{stem}-{n}.{ext}"
                break

    try:
        if ext == "docx":
            _write_docx(path, content, title=(what_it_is or "")[:120])
        elif ext == "xlsx":
            _write_xlsx(path, content)
        else:
            # temp + rename: a half-written file that Barry opens mid-write is
            # worse than no file. Same discipline as the deck patch scripts.
            tmp = path + ".part"
            with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(content)
            os.replace(tmp, path)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Could not write the file: {exc}"}

    size = os.path.getsize(path)
    aid = agent_id or _agent_id_for(office_name)
    approval_id = None
    try:
        # Same table, same endpoint that has served generated images since
        # July -- so this needs no new delivery plumbing to reach him.
        approval_id = memory.queue_for_approval(
            aid or (office_name or "unknown"),
            "file",
            f"FILE: {name}\n{what_it_is.strip()[:500]}" if what_it_is.strip() else f"FILE: {name}",
            file_path=path,
        )
        # A file TO Barry is delivered the moment it exists -- it goes straight
        # to his Out box (status approved), not Pending Review. There is
        # nothing to approve: approving would only run the learning loop and
        # write a PRIORITY fact about a file he asked for. decided_at stays
        # NULL so the row is distinguishable from a real approve click.
        if approval_id:
            with memory.get_db() as conn:
                conn.execute("UPDATE approvals SET status = 'approved' WHERE id = ?",
                             (approval_id,))
    except Exception as exc:  # noqa: BLE001
        # The file is on disk and that is what matters; the row is how it
        # SHOWS UP, so say so instead of pretending it was delivered.
        return {"saved": True, "path": path, "filename": name,
                "warning": f"Written to disk but not registered for download: {exc}"}

    result = {
        "saved": True,
        "filename": name,
        "size_bytes": size,
        "approval_id": approval_id,
        "download_url": f"/api/files/{approval_id}/download" if approval_id else "",
        "tell_barry": (
            f"'{name}' is on his DESK (the DESK panel on the dashboard) with a download button. "
            f"It is also on disk at {path}"
        ),
    }
    if ext_changed:
        result["note_on_name"] = (
            f"Saved as .{ext} -- the extension asked for is not one that can be written "
            f"here (allowed: {', '.join(WRITABLE_EXTS)}). For a PDF, he opens the .docx "
            f"and exports it."
        )
    if truncated:
        result["note_on_length"] = (
            f"The content was longer than {MAX_CHARS:,} characters and was cut. "
            f"Say so -- do not describe the file as complete."
        )
    return result


def register_file(office_name: str, src_path: str, what_it_is: str = "", agent_id: str = "") -> dict:
    """An existing file (an MP4, a STEP, a PNG a tool already made) onto his DESK: copied into the agent's folder and
    registered exactly like write_file (2026-10-17, for Vivian's product spots and Sophie's CAD parts)."""
    ensure_tree()
    if not os.path.isfile(src_path):
        return {"error": f"No such file: {src_path}"}
    name, _ext = _safe_name(os.path.basename(src_path), default_ext=os.path.splitext(src_path)[1].lstrip(".") or "bin")
    name = os.path.basename(src_path) if "." in os.path.basename(src_path) else name
    folder = _agent_dir(office_name)
    path = os.path.join(folder, name)
    if os.path.exists(path):
        stem, ext = os.path.splitext(name)
        for n in range(2, 100):
            candidate = os.path.join(folder, f"{stem}-{n}{ext}")
            if not os.path.exists(candidate):
                path, name = candidate, f"{stem}-{n}{ext}"
                break
    try:
        shutil.copy2(src_path, path)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Could not copy the file to the DESK: {exc}"}
    aid = agent_id or _agent_id_for(office_name)
    try:
        approval_id = memory.queue_for_approval(
            aid or (office_name or "unknown"), "file",
            f"FILE: {name}\n{what_it_is.strip()[:500]}" if what_it_is.strip() else f"FILE: {name}", file_path=path)
        if approval_id:
            with memory.get_db() as conn:
                conn.execute("UPDATE approvals SET status = 'approved' WHERE id = ?", (approval_id,))
    except Exception as exc:  # noqa: BLE001
        return {"saved": True, "path": path, "filename": name,
                "warning": f"Copied to the DESK folder but not registered for download: {exc}"}
    return {"saved": True, "filename": name, "size_bytes": os.path.getsize(path), "approval_id": approval_id,
            "download_url": f"/api/files/{approval_id}/download" if approval_id else "",
            "tell_barry": f"'{name}' is on his DESK (the DESK panel on the dashboard) with a download button. "
                          f"It is also on disk at {path}"}


def _agent_id_for(office_name: str) -> str:
    try:
        import agents as _agents
        return _agents.agent_id_for_office(office_name)   # hires too (2026-10-10)
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------------------
# The script export -- byte-exact, no model in the path
# ---------------------------------------------------------------------------

def export_script(office_name: str, filename: str = "", script: str = "",
                  ext: str = "md") -> dict:
    """Write the agent's whole assembled script to a file, straight from the DB.

    THE REASON THIS IS NOT write_file: the episode is ~94,000 characters and a
    model reply is capped at 4,096 tokens. An agent asked to "put the script in
    a file" using write_file would type as much as it could and hand over a
    fragment while calling it the script. Here the bytes never pass through the
    model at all.
    """
    try:
        import script_index
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Script access is not available: {exc}"}

    try:
        wanted = (script or "").strip() or script_index.default_script(office_name)
        if not wanted:
            return {"error": "No script found to export. Nothing has been written into "
                            "the working script yet."}
        # The RAW fact text, not re-joined blocks: parse_blocks() splits on the
        # rule lines and drops them, so re-joining would not be byte-exact.
        result = memory.get_skill_content(office_name, wanted)
        if not result.get("found"):
            return {"error": f"No script matching '{wanted}'.",
                    "available": [s for s in result.get("available_skills", [])
                                  if "script" in s.lower()]}
        skills = result["skills"]
        exact = [s for s in skills if s["title"].lower() == wanted.strip().lower()]
        chosen = (exact or skills)[0]
        title = chosen["title"]
        body = chosen["content"] or ""
        blocks = script_index.parse_blocks(body)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Could not assemble the script: {exc}"}

    if not body.strip():
        return {"error": f"'{title}' is empty -- nothing to export."}

    stamp = datetime.datetime.now().strftime("%Y-%m-%d")
    ext = (ext or "md").lower().strip(".")
    if ext not in WRITABLE_EXTS:
        ext = "md"
    name = (filename or f"{title}-{stamp}.{ext}").strip()

    res = write_file(office_name, name, body,
                     what_it_is=f"{title} -- full script, {len(blocks)} blocks, exported word for word")
    if res.get("saved"):
        res["blocks"] = len(blocks)
        res["script"] = title
        res["exact"] = ("Straight from the working script, word for word -- "
                        "nothing was rewritten on the way out.")
    return res


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def list_inbox() -> list[dict]:
    """Files Barry has put in drop/_files/ for the agents to read."""
    ensure_tree()
    out: list[dict] = []
    try:
        for name in sorted(os.listdir(INBOX_ROOT)):
            path = os.path.join(INBOX_ROOT, name)
            if not os.path.isfile(path) or name.startswith((".", "~", "_")):
                continue
            st = os.stat(path)
            out.append({
                "name": name,
                "size_bytes": st.st_size,
                "modified": datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
            })
    except Exception:  # noqa: BLE001
        pass
    return out


# What Barry may put on the shelf from the deck. Anything document_extract
# can read, plus the media kinds media_understanding describes. Deliberately
# no executables -- this folder is opened by the agents, not run by them, but
# a shelf is not a place for .exe/.bat either.
INBOX_EXTS = ("pdf", "docx", "doc", "xlsx", "xls", "csv", "pptx", "html", "htm",
              "rtf", "txt", "md", "json", "zip", "png", "jpg", "jpeg", "webp",
              "gif", "mp4", "mov", "mp3", "wav", "m4a")
INBOX_MAX_BYTES = 200 * 1024 * 1024


def save_to_inbox(filename: str, data: bytes) -> dict:
    """The OUT BOX door: a file uploaded from the deck lands on his shelf."""
    ensure_tree()
    if not data:
        return {"error": "That file is empty."}
    if len(data) > INBOX_MAX_BYTES:
        return {"error": f"Too big ({len(data) // (1024*1024)} MB); the shelf takes up to "
                         f"{INBOX_MAX_BYTES // (1024*1024)} MB. Put it in drop\\_files by hand."}
    raw = os.path.basename((filename or "").replace("\\", "/")).strip()
    raw = re.sub(r"[^A-Za-z0-9 ._()-]", "", raw).strip(" .") or "file"
    if "." not in raw:
        return {"error": "The file needs an extension so the agents know how to read it."}
    stem, ext = raw.rsplit(".", 1)
    if ext.lower() not in INBOX_EXTS:
        return {"error": f".{ext} is not a readable document type. Readable: "
                         f"{', '.join(INBOX_EXTS)}."}
    name = f"{stem[:100].strip(' .') or 'file'}.{ext.lower()}"
    if name.startswith("_"):
        name = name.lstrip("_") or "file." + ext.lower()
    path = os.path.join(INBOX_ROOT, name)
    if os.path.exists(path):
        for n in range(2, 100):
            cand = os.path.join(INBOX_ROOT, f"{stem[:100]}-{n}.{ext.lower()}")
            if not os.path.exists(cand):
                path, name = cand, os.path.basename(cand)
                break
    try:
        tmp = path + ".part"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Could not save it: {exc}"}
    return {"saved": True, "name": name, "size_bytes": len(data),
            "note": "On the shelf. Tell any agent to read it by name."}


def delete_inbox_file(name: str) -> dict:
    safe = os.path.basename((name or "").replace("\\", "/"))
    if not safe or safe.startswith("_"):
        return {"error": "No such file."}
    path = os.path.join(INBOX_ROOT, safe)
    if not os.path.isfile(path):
        return {"error": f"No file called '{safe}' on the shelf."}
    try:
        os.remove(path)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Could not remove it: {exc}"}
    return {"removed": True, "name": safe}


def read_inbox_file(name: str, max_chars: int = 40_000, start_char: int = 0) -> dict:
    """Read one file from Barry's shelf as text.

    Chunked for the same reason read_project_file is (2026-08-16): an
    uncapped read of a big document blew past the context window, and
    llama-server 400s honestly where Ollama silently truncates -- which is
    how an agent ends up confidently answering from half a document.
    """
    ensure_tree()
    safe = os.path.basename((name or "").replace("\\", "/"))
    if not safe:
        return {"error": "Which file? Call list_files first."}
    path = os.path.join(INBOX_ROOT, safe)
    if not os.path.isfile(path):
        available = [f["name"] for f in list_inbox()]
        return {"error": f"There is no file called '{safe}' in Barry's files.",
                "available": available or ["(the folder is empty)"]}
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Could not open it: {exc}"}

    if safe.lower().endswith((".md", ".txt", ".json", ".log")):
        text = data.decode("utf-8", errors="replace")
    else:
        try:
            import document_extract
            text = document_extract.extract_text(safe, data)
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Could not read that file type: {exc}"}

    total = len(text)
    start = max(0, int(start_char or 0))
    cap = max(1_000, min(int(max_chars or 40_000), 40_000))
    chunk = text[start:start + cap]
    res = {"file": safe, "total_chars": total, "text": chunk}
    if start + len(chunk) < total:
        res["more"] = True
        res["next_start_char"] = start + len(chunk)
        res["note"] = (f"Showing characters {start:,}-{start + len(chunk):,} of {total:,}. "
                       f"Call read_barrys_file again with start_char={start + len(chunk)} "
                       f"for the rest. Do not summarise it as if you read all of it.")
    return res


# ---------------------------------------------------------------------------
# Listing what agents have made (powers the FILES panel + the list tool)
# ---------------------------------------------------------------------------

def list_agent_files(office_name: str = "") -> list[dict]:
    """Every file on disk under data/agent_files/, newest first.

    Reads the DISK, not the approvals table, so a file stays listed and
    downloadable even if its row was cleared -- and a row whose file was
    deleted by hand cannot show up as a download that 404s.
    """
    ensure_tree()
    rows: list[dict] = []
    try:
        folders = ([office_name] if office_name
                   else sorted(os.listdir(FILES_ROOT)))
    except Exception:  # noqa: BLE001
        return rows

    # One pass over the approvals table so each file can carry its download id.
    by_path: dict[str, int] = {}
    try:
        with memory.get_db() as conn:
            for r in conn.execute(
                    "SELECT id, file_path FROM approvals WHERE action_type = 'file' "
                    "AND file_path != '' ORDER BY id DESC"):
                by_path.setdefault(os.path.normcase(r["file_path"]), r["id"])
    except Exception:  # noqa: BLE001
        pass

    for folder in folders:
        fdir = os.path.join(FILES_ROOT, folder)
        if not os.path.isdir(fdir) or folder.startswith("_"):
            continue          # _trash and any other housekeeping folder are not a seat
        for name in os.listdir(fdir):
            path = os.path.join(fdir, name)
            if not os.path.isfile(path) or name.endswith(".part"):
                continue
            try:
                st = os.stat(path)
            except Exception:  # noqa: BLE001
                continue
            rows.append({
                "office": folder,
                "agent_id": _agent_id_for(folder),
                "name": name,
                "size_bytes": st.st_size,
                "modified": datetime.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                "mtime": st.st_mtime,
                "approval_id": by_path.get(os.path.normcase(path)),
                "path": path,
            })
    rows.sort(key=lambda r: r["mtime"], reverse=True)
    for r in rows:
        r.pop("mtime", None)
    return rows


def resolve_download(approval_id: int) -> str | None:
    """approval id -> a real path, or None. Refuses anything outside
    FILES_ROOT so the download endpoint can never be talked into serving an
    arbitrary file off the disk by id."""
    try:
        row = memory.get_output_by_id(int(approval_id))
    except Exception:  # noqa: BLE001
        return None
    if not row:
        return None
    path = (row.get("file_path") or "").strip()
    if not path or not os.path.isfile(path):
        return None
    try:
        real = os.path.realpath(path)
        root = os.path.realpath(FILES_ROOT)
        if os.path.commonpath([real, root]) != root:
            return None
    except Exception:  # noqa: BLE001
        return None
    return path


def delete_desk_file(approval_id: int) -> dict:
    """Take a file off Barry's desk (2026-09-11: "once i read or download, i
    need to be able to delete them"). Same id-only, inside-FILES_ROOT
    resolution as the download. The file is DESTROYED (Barry, 2026-09-13:
    "not recoverable. actually gone" -- the _trash folder version is dead)
    and the approval row is marked 'deleted' so it stops being a download
    target. Never raises."""
    path = resolve_download(approval_id)
    if not path:
        return {"error": "No such file on your desk (or it is already gone)."}
    try:
        os.remove(path)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Could not delete it: {exc}"}
    try:
        with memory.get_db() as conn:
            conn.execute("UPDATE approvals SET status = 'deleted' WHERE id = ? AND action_type = 'file'",
                         (int(approval_id),))
    except Exception:  # noqa: BLE001
        pass
    return {"removed": True, "name": os.path.basename(path), "gone": not os.path.exists(path)}


def stats() -> dict:
    files = list_agent_files()
    return {
        "files": len(files),
        "inbox": len(list_inbox()),
        "files_root": FILES_ROOT,
        "inbox_root": INBOX_ROOT,
        "total_bytes": sum(f["size_bytes"] for f in files),
    }
