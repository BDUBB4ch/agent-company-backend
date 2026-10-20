"""
Turns a dropped file into plain text so it can go straight into an agent's
brain via memory.add_fact -- the web dashboard's version of what the Godot
app already does client-side (see memory_store.gd's _extract_pdf/_extract_
docx/etc). Done server-side here with real Python libraries (pypdf,
python-docx, openpyxl, python-pptx) instead of hand-rolled parsing, since
the backend can just pip install them rather than bundle a poppler binary
or hand-parse OOXML like the GDScript side had to.

extract_text() never raises for an unsupported/corrupt file -- it returns a
readable "[Could not extract ...]" message instead, the same fails-soft
pattern used everywhere else optional in this project (AmuseBridge down,
SearXNG down, etc). A failed extraction still gets stored as a fact (so
there's a record something was dropped), it just won't have useful content.
"""
import csv
import io
import re
import zipfile

from pypdf import PdfReader
import docx
import openpyxl
from pptx import Presentation

_TAG_RE = re.compile(r"<[^>]+>")
_RTF_CONTROL_RE = re.compile(r"\\[a-zA-Z]+-?\d* ?|[{}]|\\'[0-9a-fA-F]{2}|\\")

# Real gap found and fixed: the old Godot app (memory_store.gd) could unzip
# a dropped .zip and extract each contained file individually -- that never
# got rebuilt when the web dashboard replaced it, so a dropped zip here
# just fell through to the plain-text fallback and stored garbled binary
# bytes as if they were real content. Safety caps here (not present in the
# old Godot version, which used a scratch temp file on disk instead of
# working in memory) guard against a zip bomb or a huge archive blowing out
# an agent's brain with one drop -- same "don't let one bad input wreck
# everything" spirit as MAX_FILE_CHARS in read_project_file.py.
_ZIP_MAX_ENTRIES = 30
_ZIP_MAX_ENTRY_BYTES = 20 * 1024 * 1024  # 20MB per file inside the zip
_ZIP_MAX_TOTAL_CHARS = 100_000  # combined extracted text across all entries


def _extract_pdf(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    text = "\n".join(pages).strip()
    if text:
        return text
    # SCANNED PDF (2026-09-24): no text layer -> render the pages and READ them (ocr.py, CPU,
    # about 1.5 s a page). Before this, a scanned book came back empty.
    import ocr
    read = ocr.read_pdf(data)
    return read or "[PDF produced no extractable text -- a scanned image, and the text reader found nothing readable either]"


def _extract_docx(data: bytes) -> str:
    document = docx.Document(io.BytesIO(data))
    return "\n".join(p.text for p in document.paragraphs).strip()


def _extract_xlsx(data: bytes) -> str:
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    lines = []
    for sheet in wb.worksheets:
        lines.append(f"--- Sheet: {sheet.title} ---")
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c) for c in row if c is not None]
            if cells:
                lines.append(", ".join(cells))
    return "\n".join(lines).strip()


def _extract_csv(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    return "\n".join(", ".join(row) for row in reader).strip()


def _extract_pptx(data: bytes) -> str:
    prs = Presentation(io.BytesIO(data))
    lines = []
    for i, slide in enumerate(prs.slides, start=1):
        lines.append(f"--- Slide {i} ---")
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    line = "".join(run.text for run in para.runs)
                    if line.strip():
                        lines.append(line)
    return "\n".join(lines).strip()


def _extract_html(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace")
    return _TAG_RE.sub(" ", text).strip()


def _extract_rtf(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace")
    return _RTF_CONTROL_RE.sub(" ", text).strip()


def _extract_plain(data: bytes) -> str:
    return data.decode("utf-8", errors="replace").strip()


# Nested-zip depth cap -- a zip containing a zip containing a zip is a real,
# if unlikely, way to force runaway recursion (extract_text -> _extract_zip
# -> extract_text -> ...) since each contained file just gets routed back
# through the same dispatch. This isn't a public-facing upload endpoint
# (Barry's own dashboard, his own files), but the cap is free insurance.
_ZIP_MAX_DEPTH = 3


def _walk_zip_entries(data: bytes, _depth: int = 0) -> list[dict]:
    """Shared core for _extract_zip (joined-text, unchanged public
    behavior) and extract_zip_entries (structured, for Priya's real
    per-file delegation -- see main.py) -- one real walk of the archive,
    not two separate implementations that could drift apart. Each dict is
    {"filename", "text"} or {"filename", "note"} for a skipped/failed entry
    (kept out of the real per-file list so a skip note never gets treated
    as real delegable content)."""
    if _depth >= _ZIP_MAX_DEPTH:
        return [{"filename": "", "note": f"Nested zip skipped -- more than {_ZIP_MAX_DEPTH} levels deep"}]
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return [{"filename": "", "note": "Could not open zip -- file is corrupt or not actually a zip archive"}]

    entries = [
        info for info in zf.infolist()
        if not info.is_dir()
        and not info.filename.startswith("__MACOSX/")
        and not info.filename.rsplit("/", 1)[-1].startswith(".")
    ]
    if not entries:
        return [{"filename": "", "note": "Zip archive contains no readable files"}]

    results = []
    total_chars = 0
    processed = 0
    for info in entries:
        if processed >= _ZIP_MAX_ENTRIES:
            results.append({"filename": "", "note": f"{len(entries) - processed} more file(s) in this zip were not processed -- {_ZIP_MAX_ENTRIES}-file limit reached"})
            break
        if total_chars >= _ZIP_MAX_TOTAL_CHARS:
            results.append({"filename": "", "note": "Remaining files in this zip were not processed -- combined content limit reached"})
            break
        if info.file_size > _ZIP_MAX_ENTRY_BYTES:
            results.append({"filename": info.filename, "note": f"Skipped -- larger than {_ZIP_MAX_ENTRY_BYTES // (1024 * 1024)}MB"})
            processed += 1
            continue
        try:
            entry_bytes = zf.read(info.filename)
        except Exception as e:
            results.append({"filename": info.filename, "note": f"Could not read: {e}"})
            processed += 1
            continue
        # Recurses through extract_text -- a .docx/.pdf/.xlsx/etc inside the
        # zip gets the exact same real extraction as if dropped on its own,
        # and a .zip inside a zip is handled too (bounded by _ZIP_MAX_DEPTH
        # above), not just flattened to garbled bytes.
        entry_text = extract_text(info.filename, entry_bytes, _depth=_depth + 1)
        results.append({"filename": info.filename, "text": entry_text})
        total_chars += len(entry_text)
        processed += 1

    return results


def _extract_zip(data: bytes, _depth: int = 0) -> str:
    entries = _walk_zip_entries(data, _depth)
    sections = []
    for e in entries:
        if "text" in e:
            sections.append(f"--- File: {e['filename']} ---\n{e['text']}")
        else:
            sections.append(f"[{e['note']}]" if not e["filename"] else f"--- File: {e['filename']} ---\n[{e['note']}]")
    return "\n\n".join(sections)


def extract_zip_entries(data: bytes) -> list[dict]:
    """Public, structured version for real per-file delegation (see
    main.py's Priya-delegation path) -- only real, successfully-extracted
    files, skip/error notes filtered out since there's nothing delegable
    about them."""
    return [e for e in _walk_zip_entries(data) if "text" in e]


_EXTRACTORS = {
    "pdf": _extract_pdf,
    "docx": _extract_docx,
    "xlsx": _extract_xlsx,
    "xls": _extract_xlsx,
    "csv": _extract_csv,
    "pptx": _extract_pptx,
    "html": _extract_html,
    "htm": _extract_html,
    "zip": _extract_zip,
    "rtf": _extract_rtf,
}


def is_media(filename: str) -> bool:
    """Whether extract_text will route this file through media_understanding
    rather than a text extractor. Callers need this to decide where the result
    should live in the brain -- see the upload endpoint in main.py."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    try:
        import media_understanding as mu
        return ext in mu.IMAGE_EXTS or ext in mu.VIDEO_EXTS or ext in mu.AUDIO_EXTS
    except Exception:
        return False


def extract_text(filename: str, data: bytes, _depth: int = 0) -> str:
    # Images and video route through media_understanding first -- an image's
    # "text" is what a vision model reports is actually in it, and a video's is
    # a timeline of frame descriptions plus audio levels and any speech. Before
    # this existed a dropped PNG fell through to _extract_plain and was stored
    # as garbled UTF-8, which is why the agents could describe the Talia Crew
    # from prose someone typed for them but had never seen a single render.
    # Deliberately first in the chain and fails soft: if the vision model is
    # unreachable the media path returns its own "[...]" note rather than
    # raising, and anything that is not media returns None and falls straight
    # through to the existing extractors untouched.
    try:
        import media_understanding
        media_text = media_understanding.understand_media_bytes(filename, data)
        if media_text is not None:
            return media_text
    except Exception as e:
        return f"[Could not read media '{filename}': {e}]"

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    extractor = _EXTRACTORS.get(ext, _extract_plain)
    try:
        # _depth only ever matters for _extract_zip (nested-zip guard) --
        # every other extractor's signature is just (data), so it's only
        # passed when the extractor is actually the zip one.
        text = extractor(data, _depth) if extractor is _extract_zip else extractor(data)
    except Exception as e:
        return f"[Could not extract text from '{filename}': {e}]"
    return text or f"[No extractable text found in '{filename}']"
