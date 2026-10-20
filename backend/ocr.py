"""READING THE TEXT IN IMAGES (2026-09-24, Barry: "i need the office to be able to read photos and
videos" -> "what i mean by read is see the image and read texts" -> "ok lets get the best for us").

The office could already SEE a picture (media_understanding.describe_image, the vision model), but a
vision model skims text: fine for "BIONOVA" on a label, unreliable on a book page (paraphrases, invents).
This reads the text EXACTLY, line by line: RapidOCR 3.9.2 with its bundled PP-OCRv6 models (Apache-2.0,
ONNX Runtime, CPU only -- no GPU, no network, no API). Measured on his own photos: 1.3-1.5 s per image,
book titles read word for word.

Used by: media_understanding.understand_image / understand_video / look_at_product_photo /
look_at_render, and document_extract for scanned PDFs (no text layer). Never raises -- a failed read
returns "" and the caller simply shows no text section.
"""
from __future__ import annotations

import io
import threading

_engine = None
_lock = threading.Lock()          # one engine, one image at a time (ONNX session reuse)
MIN_SCORE = 0.5                   # drop low-confidence scraps (angled/tiny print that reads as noise)


def _get():
    global _engine
    if _engine is None:
        import logging
        logging.getLogger("RapidOCR").setLevel(logging.WARNING)   # its INFO lines flood the backend log
        from rapidocr import RapidOCR
        _engine = RapidOCR()
        for name in ("RapidOCR", "rapidocr"):                      # it resets its level at start-up
            logging.getLogger(name).setLevel(logging.WARNING)
    return _engine


def _columns(items, width: float) -> list[list[tuple]]:
    """Split into side-by-side columns wherever a vertical gap runs top to bottom that NO text box
    crosses (two-column book pages, several books in one photo). One column when there is no gap."""
    spans = sorted((i[2], i[4]) for i in items)
    cols, cur_end, cuts = [], None, []
    for x0, x1 in spans:
        if cur_end is not None and x0 - cur_end > max(12.0, 0.02 * width):
            cuts.append((cur_end + x0) / 2)
        cur_end = x1 if cur_end is None else max(cur_end, x1)
    edges = [-1e9] + cuts + [1e9]
    for a, b in zip(edges, edges[1:]):
        col = [i for i in items if a <= (i[2] + i[4]) / 2 < b]
        if col:
            cols.append(col)
    return cols


def _lines(items) -> list[str]:
    """Group detections into lines (top to bottom), each line left to right."""
    items = sorted(items, key=lambda i: (i[0], i[2]))
    lines: list[list[tuple]] = []
    for it in items:
        if lines:
            top, bot = min(x[0] for x in lines[-1]), max(x[1] for x in lines[-1])
            h = max(1.0, bot - top)
            if it[0] < bot - 0.4 * h:                    # vertically overlaps the current line
                lines[-1].append(it)
                continue
        lines.append([it])
    return [" ".join(x[3] for x in sorted(line, key=lambda i: i[2])) for line in lines]


def _in_reading_order(boxes, txts, scores, width: float) -> list[str]:
    """Columns left to right; inside each, lines top to bottom, words left to right."""
    items = []
    for box, t, s in zip(boxes, txts, scores):
        if not t or (s is not None and float(s) < MIN_SCORE):
            continue
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        items.append((min(ys), max(ys), min(xs), t.strip(), max(xs)))
    cols = _columns(items, width)
    out = []
    for n, col in enumerate(cols):
        if len(cols) > 1:
            out.append(f"[column {n + 1}]")
        out.extend(_lines(col))
    return out


def read_image(data: bytes) -> str:
    """Exact text in an image (bytes of png/jpg/webp/...), in reading order. "" if none/failed."""
    try:
        from PIL import Image
        import numpy as np
        img = Image.open(io.BytesIO(data)).convert("RGB")
        with _lock:
            r = _get()(np.array(img))
        if r is None or r.txts is None or r.boxes is None:
            return ""
        return "\n".join(_in_reading_order(r.boxes, r.txts, r.scores, float(img.width))).strip()
    except Exception:                                   # noqa: BLE001 -- never break the caller
        return ""


def read_pdf(data: bytes, max_pages: int = 500, scale: float = 2.0) -> str:
    """Scanned PDF (no text layer): render each page to an image and read it. "" if nothing read."""
    try:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(data)
        out = []
        for i in range(min(len(pdf), max_pages)):
            page = pdf[i]
            pil = page.render(scale=scale).to_pil()
            buf = io.BytesIO()
            pil.save(buf, "PNG")
            txt = read_image(buf.getvalue())
            if txt:
                out.append(f"--- page {i + 1} ---\n{txt}")
        return "\n\n".join(out).strip()
    except Exception:                                   # noqa: BLE001
        return ""
