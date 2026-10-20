"""Add a PDF book to THE LIBRARY (backend/library.py), split into sections by its own table of contents.

  python scripts/library_add_pdf.py <pdf> --slug lost-book-of-herbal-remedies --title "..." --author "..."
         --year 2019 --readers ilnora --trust "..."

Finds the contents pages (lines ending in a page number), works out the printed-page -> PDF-page offset, and cuts
the text at each entry's own heading. Long sections are split into parts. Nothing leaves the machine.
"""
import argparse
import json
import os
import re
import shutil

import pypdfium2 as pdfium

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "data", "library")
PART = 12000
TOC_LINE = re.compile(r"^\s*(.{3,90}?)[\s.…·_]{1,}(\d{1,3})\s*$")


def clean(t: str) -> str:
    t = t.replace("￾\r\n", "").replace("￾\n", "").replace("￾", "").replace("­", "")
    t = t.replace("\r", "")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    for k in ("slug", "title", "author", "year", "trust"):
        ap.add_argument(f"--{k}", default="")
    ap.add_argument("--readers", default="ilnora")
    ap.add_argument("--header", default="", help="running header text to strip from every page")
    a = ap.parse_args()

    doc = pdfium.PdfDocument(a.pdf)
    pages = [clean(doc[i].get_textpage().get_text_range()) for i in range(len(doc))]
    header = a.header or a.title
    def strip_page(t):
        lines = [ln for ln in t.split("\n") if ln.strip() and ln.strip() != header.strip()
                 and not re.fullmatch(r"\d{1,3}", ln.strip())
                 and not (header and ln.strip().startswith(header.strip()) and len(ln.strip()) < len(header) + 6)]
        return "\n".join(lines)
    body = [strip_page(t) for t in pages]

    # contents pages = early pages with many "title .... N" lines
    toc_pages = [i for i in range(min(15, len(pages)))
                 if sum(bool(TOC_LINE.match(ln)) for ln in pages[i].split("\n")) >= 6]
    entries = []
    for i in toc_pages:
        for ln in pages[i].split("\n"):
            m = TOC_LINE.match(ln)
            if m:
                title = m.group(1).strip(" .…-")
                if title.lower() not in ("table of contents", "contents", "disclaimer") and len(title) > 2:
                    entries.append((title, int(m.group(2))))
    entries = [e for e in entries if e[1] > 0]
    # offset: printed page p is PDF index p + off
    def key(title):
        return re.split(r"[,(]", title)[0].strip().lower()[:24]
    best = max(range(-3, 8), key=lambda off: sum(
        1 for t, p in entries if 0 <= p + off < len(body) and key(t) in body[p + off].lower()))
    print(f"{len(entries)} entries, contents on PDF pages {[i + 1 for i in toc_pages]}, offset {best}")

    # sort by page, keep order within a page as listed
    entries = sorted(enumerate(entries), key=lambda x: (x[1][1], x[0]))
    entries = [e for _, e in entries]
    first_body = max(toc_pages) + 1 if toc_pages else 0
    sections = []
    out = os.path.join(LIB, a.slug)
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    n = 0
    for k, (title, p) in enumerate(entries):
        s_idx = max(first_body, p + best)
        nxt = entries[k + 1][1] + best if k + 1 < len(entries) else len(body) - 1
        e_idx = max(s_idx, nxt)
        chunk = "\n".join(body[s_idx:e_idx + 1])
        low = chunk.lower()
        # cut at HEADINGS only (the title starting a line) -- a mention inside a paragraph is not a heading
        def heading_at(k_, frm=0):
            m_ = re.compile(r"(?m)^[ 	]*" + re.escape(k_)).search(low, frm)
            return m_.start() if m_ else -1
        start = heading_at(key(title))
        start = start if start >= 0 else 0
        end = len(chunk)
        if k + 1 < len(entries):
            nk = key(entries[k + 1][0])
            j = heading_at(nk, start + max(1, len(key(title))))
            if j > start:
                end = j
            elif nxt > s_idx:          # next entry's heading not found: stop at its page
                end = len("\n".join(body[s_idx:nxt]))
        text = chunk[start:end].strip()
        if len(text) < 40:
            continue
        words = re.findall(r"[A-Za-z][A-Za-z'-]+", title)
        labels = re.findall(r"^\s*([A-Z][A-Za-z ,/'()-]{2,40}):", text, re.M)
        keywords = sorted({w.lower() for w in words} | {lbl.strip().lower() for lbl in labels})[:80]
        parts = [text[i:i + PART] for i in range(0, len(text), PART)]
        for pi, part in enumerate(parts):
            n += 1
            name = title if len(parts) == 1 else f"{title} (part {pi + 1} of {len(parts)})"
            fn = f"{n:03d}.txt"
            with open(os.path.join(out, fn), "w", encoding="utf-8") as fh:
                fh.write(part)
            sections.append({"id": n, "title": name, "pages": f"{p}", "keywords": keywords, "file": fn})
    book = {"title": a.title, "author": a.author, "year": a.year, "pages": len(pages),
            "readers": [r.strip() for r in a.readers.split(",") if r.strip()], "trust": a.trust,
            "source_file": os.path.basename(a.pdf), "sections": sections}
    json.dump(book, open(os.path.join(out, "book.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    sizes = [len(open(os.path.join(out, s["file"]), encoding="utf-8").read()) for s in sections]
    print(f"{len(sections)} sections, {sum(sizes):,} chars kept of {sum(len(b) for b in body):,}; "
          f"smallest {min(sizes)}, largest {max(sizes)}")


main()
