"""Remove baked-in letterbox/pillarbox bars from a LoRA dataset folder.

Found 2026-08-04: 17 of Vor'Shara's 27 original frames were squared up by
padding with black bars down both sides. Those bars are training signal --
the model learns a dark vignette as part of the character.

NOTHING IS DELETED. Originals are copied to <folder>/_prebar_originals/ before
anything is overwritten, so this is fully reversible. Barry's rule stands:
"nothing is redundant, its always useful".

Why bars are not simply cropped to a rectangle: the trainer's dataset loader
wants consistent square inputs, and centre-cropping a full-body frame to a
square cuts her head or her hem off. Instead the bars are removed and the real
content is re-padded to square with the frame's OWN background tone, sampled
from the content edge -- so the padding is invisible instead of black.

Usage:
    python scripts/fix_pillarbox.py lora_vorshara --preview-dir data/_barfix
    python scripts/fix_pillarbox.py lora_vorshara --write
"""
import argparse
import pathlib
import shutil

from PIL import Image, ImageStat

ROOT = pathlib.Path(__file__).resolve().parent.parent
INPUT = ROOT / "tools" / "ComfyUI" / "input"


def bar_extent(im):
    """Columns of leading/trailing bar. Returns (left, right) pixel counts."""
    g = im.convert("L")
    w, h = g.size
    col = [ImageStat.Stat(g.crop((x, 0, x + 1, h))).mean[0] for x in range(w)]
    mid = sorted(col)[len(col) // 2]
    # a bar column is much darker than the typical column of this image
    cut = min(mid * 0.5, 60)
    left = 0
    while left < w and col[left] < cut:
        left += 1
    right = 0
    while right < w and col[w - 1 - right] < cut:
        right += 1
    return left, right


def fix(im):
    w, h = im.size
    left, right = bar_extent(im)
    if left + right < w * 0.02:
        return None, (left, right)
    content = im.crop((left, 0, w - right, h))
    cw, ch = content.size
    # sample the background from the content's own outer edge, so the new
    # padding matches the studio backdrop instead of introducing black
    edge = Image.new("RGB", (cw, 8))
    edge.paste(content.crop((0, 0, cw, 4)), (0, 0))
    edge.paste(content.crop((0, ch - 4, cw, ch)), (0, 4))
    bg = tuple(int(v) for v in ImageStat.Stat(edge).median[:3])

    scale = min(w / cw, h / ch)
    new = content.resize((int(cw * scale), int(ch * scale)), Image.LANCZOS)
    out = Image.new("RGB", (w, h), bg)
    out.paste(new, ((w - new.size[0]) // 2, (h - new.size[1]) // 2))
    return out, (left, right)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--preview-dir")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    src = INPUT / args.folder
    if not src.is_dir():
        ap.error(f"no such folder: {src}")
    if not args.write and not args.preview_dir:
        ap.error("give --preview-dir to look first, or --write to commit")

    backup = src / "_prebar_originals"
    prev = pathlib.Path(args.preview_dir) if args.preview_dir else None
    if prev:
        prev.mkdir(parents=True, exist_ok=True)

    hits = 0
    for p in sorted(src.glob("*.png")):
        im = Image.open(p).convert("RGB")
        out, (l, r) = fix(im)
        if out is None:
            continue
        hits += 1
        print(f"{p.name:<14} bars L={l:<4} R={r:<4} -> content {im.size[0]-l-r}px wide")
        if prev:
            out.save(prev / p.name)
        if args.write:
            backup.mkdir(exist_ok=True)
            if not (backup / p.name).exists():
                shutil.copy2(p, backup / p.name)
            out.save(p)

    print(f"\n{hits} frame(s) with bars")
    if args.write:
        print(f"originals preserved in {backup}")
    else:
        print(f"preview only -- nothing written. look in {prev}")


if __name__ == "__main__":
    main()
