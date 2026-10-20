"""Split multi-panel character sheets into single-subject panels.

Written 2026-08-04 for the Keth dataset. Character sheets fed in WHOLE are the
documented cause of the first failed B Dubb LoRA (the model learned collage
layout and averaged faces instead of the character), so every sheet has to be
cut into single-subject panels before training. The older scratchpad/prep_bdubb.py
referenced in memory no longer exists on disk -- this replaces it.

Panels here butt against each other with thin light gutters rather than wide
white margins, and a vertical gutter usually spans only ONE row band (e.g. a
2-panel top row over a 3-panel bottom row), which is why a naive full-height
column scan finds nothing. So: find horizontal gutters first, split into row
bands, then look for vertical gutters WITHIN each band.

Dry run by default -- pass --write to actually create files.
"""
import argparse
import pathlib
import sys

import numpy as np
from PIL import Image, ImageDraw

# A panel much wider than tall is a prop shot, a two-figure panel, or a
# mis-detected merge -- the documented reject rule from the B Dubb post-mortem.
MAX_ASPECT = 1.4
MIN_PANEL_PX = 180


def trim_borders(gray):
    """Strip the uniform letterbox bars so gutter stats aren't dragged by them."""
    h, w = gray.shape
    border = gray[0, 0]

    def uniform(v):
        return v.std() < 6 and abs(v.mean() - border) < 12

    top = 0
    while top < h - 1 and uniform(gray[top]):
        top += 1
    bot = h - 1
    while bot > top and uniform(gray[bot]):
        bot -= 1
    left = 0
    while left < w - 1 and uniform(gray[:, left]):
        left += 1
    right = w - 1
    while right > left and uniform(gray[:, right]):
        right -= 1
    return top, bot, left, right


def _runs(indices):
    out = []
    for i in indices:
        if out and i == out[-1][1] + 1:
            out[-1][1] = i
        else:
            out.append([i, i])
    return out


def _gutters(strip, axis, std_max, mean_min):
    """Indices along `axis` that look like a separator line: low variance and
    brighter than the artwork around them."""
    n = strip.shape[axis]
    hits = []
    for i in range(n):
        line = strip[i, :] if axis == 0 else strip[:, i]
        if line.std() < std_max and line.mean() > mean_min:
            hits.append(i)
    return _runs(hits)


def _cuts_from_gutters(runs, length):
    """Turn gutter runs into (start, end) panel spans, dropping slivers."""
    spans, prev = [], 0
    for s, e in runs:
        if s - prev >= MIN_PANEL_PX:
            spans.append((prev, s - 1))
        prev = e + 1
    if length - prev >= MIN_PANEL_PX:
        spans.append((prev, length - 1))
    return spans


def _strongest_step(profile, lo, hi):
    """Column index of the sharpest tonal discontinuity in [lo, hi).

    These sheets mostly do NOT use white gutters -- panels butt together and
    the only evidence of a seam is a step in the column-mean brightness (Keth
    013 drops 146 -> 127 across x=512). Threshold-based gutter detection is
    blind to that, so we look for the edge itself.
    """
    best, best_score = None, 0.0
    for x in range(lo, hi):
        left = profile[max(0, x - 4):x].mean()
        right = profile[x + 1:x + 5].mean()
        score = abs(right - left)
        if score > best_score:
            best, best_score = x, score
    return best, best_score


def _split_wide(band, x0, cw, min_score=6.0):
    """Recursively halve a band at its sharpest seam until every piece is
    within MAX_ASPECT. Returns a list of (cx0, cx1) column spans."""
    w = band.shape[1]
    h = band.shape[0]
    if w / h <= MAX_ASPECT or w < 2 * MIN_PANEL_PX:
        return [(x0, x0 + w - 1)]
    profile = band.mean(axis=0)
    lo, hi = int(w * 0.25), int(w * 0.75)
    cut, score = _strongest_step(profile, lo, hi)
    if cut is None or score < min_score:
        cut = w // 2  # regular grid fallback
    left = _split_wide(band[:, :cut], x0, cw, min_score)
    right = _split_wide(band[:, cut + 1:], x0 + cut + 1, cw, min_score)
    return left + right


def panels_from_layout(path, rows, margin=10):
    """Split on an EXPLICIT grid, e.g. rows=[2, 3] for a 2-panel top row over a
    3-panel bottom row.

    This is deliberately dumber than the detectors above, and it is the one
    that actually works. These sheets separate panels with a tonal step rather
    than a gutter, and a step detector reliably locks onto the highest-contrast
    edge INSIDE the artwork -- the character's own body -- slicing figures in
    half (verified by eye on the Keth sheets: 7 of 8 auto-splits were wrong).
    The grids are regular, so state the grid and cut evenly.

    margin trims a few pixels off each panel edge so a sliver of the neighbour
    doesn't bleed in.
    """
    gray = np.asarray(Image.open(path).convert("L")).astype(float)
    top, bot, left, right = trim_borders(gray)
    ch = bot - top + 1
    cw = right - left + 1

    panels = []
    rh = ch / len(rows)
    for r, ncols in enumerate(rows):
        y0 = int(top + r * rh) + margin
        y1 = int(top + (r + 1) * rh) - margin
        colw = cw / ncols
        for c in range(ncols):
            x0 = int(left + c * colw) + margin
            x1 = int(left + (c + 1) * colw) - margin
            panels.append((x0, y0, x1, y1))
    return panels


def find_panels(path, std_max=28, mean_min=150):
    """Returns a list of (x0, y0, x1, y1) panel boxes in ORIGINAL image coords."""
    gray = np.asarray(Image.open(path).convert("L")).astype(float)
    top, bot, left, right = trim_borders(gray)
    content = gray[top:bot + 1, left:right + 1]
    ch, cw = content.shape

    hruns = _gutters(content, 0, std_max, mean_min)
    bands = _cuts_from_gutters(hruns, ch)
    if not bands:
        bands = [(0, ch - 1)]
    # No bright horizontal gutter either? Look for the tonal step instead.
    if len(bands) == 1 and ch / cw > MAX_ASPECT:
        prof = content.mean(axis=1)
        cut, score = _strongest_step(prof, int(ch * 0.25), int(ch * 0.75))
        if cut and score >= 6.0:
            bands = [(0, cut - 1), (cut + 1, ch - 1)]

    panels = []
    for by0, by1 in bands:
        strip = content[by0:by1 + 1, :]
        vruns = _gutters(strip, 1, std_max, mean_min)
        cols = _cuts_from_gutters(vruns, cw)
        if not cols:
            cols = [(0, cw - 1)]
        # A span still too wide means the seam was tonal, not a bright gutter.
        refined = []
        for cx0, cx1 in cols:
            refined += _split_wide(strip[:, cx0:cx1 + 1], cx0, cw)
        for cx0, cx1 in refined:
            panels.append((left + cx0, top + by0, left + cx1, top + by1))
    return panels


def preview(path, panels, out_path):
    im = Image.open(path).convert("RGB")
    d = ImageDraw.Draw(im)
    for i, (x0, y0, x1, y1) in enumerate(panels):
        d.rectangle([x0, y0, x1, y1], outline=(255, 220, 0), width=6)
        d.text((x0 + 12, y0 + 12), str(i), fill=(255, 220, 0))
    im.save(out_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("sheets", nargs="+",
                    help="stems, optionally with a layout: 011=2,3 013=2,2 "
                         "(column count per row). Bare stem = auto-detect.")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--caption", default="@Keth")
    ap.add_argument("--preview-dir", default=None)
    args = ap.parse_args()

    folder = pathlib.Path(args.folder)
    kept = 0
    for spec in args.sheets:
        stem, _, layout = spec.partition("=")
        src = folder / f"{stem}.png"
        if not src.exists():
            print(f"{stem}: MISSING", file=sys.stderr)
            continue
        if layout:
            panels = panels_from_layout(src, [int(n) for n in layout.split(",")])
        else:
            panels = find_panels(src)
        good, rejected = [], []
        for box in panels:
            w, h = box[2] - box[0] + 1, box[3] - box[1] + 1
            (good if w / h <= MAX_ASPECT else rejected).append((box, w, h))

        print(f"{stem}: {len(panels)} panels -> keep {len(good)}, reject {len(rejected)}")
        for box, w, h in good:
            print(f"    keep   {w}x{h} ar={w/h:.2f} at {box}")
        for box, w, h in rejected:
            print(f"    REJECT {w}x{h} ar={w/h:.2f} (wider than {MAX_ASPECT}:1)")

        if args.preview_dir:
            pd = pathlib.Path(args.preview_dir)
            pd.mkdir(parents=True, exist_ok=True)
            preview(src, [b for b, _, _ in good], pd / f"preview_{stem}.png")

        if args.write:
            for i, (box, _, _) in enumerate(good):
                out = folder / f"{stem}_p{i}.png"
                Image.open(src).crop((box[0], box[1], box[2] + 1, box[3] + 1)).save(out)
                (folder / f"{stem}_p{i}.txt").write_text(args.caption, encoding="utf-8")
                kept += 1

    if args.write:
        print(f"\nwrote {kept} panel files")


if __name__ == "__main__":
    main()
