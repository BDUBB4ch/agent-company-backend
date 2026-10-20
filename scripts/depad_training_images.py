"""Remove the white padding I added, and stop forcing square frames.

WHY (2026-08-08, after keth v5 learned essentially nothing):
A no-LoRA control render was indistinguishable from a v5 render -- the LoRA was
contributing almost nothing. Measured cause:

    dataset          mean white   outcome
    lora_keth            0.3%     worked
    lora_vorshara        0.1%     worked
    lora_bdubb           6.7%     worked
    lora_keth_v5        28.5%     learned nothing
    lora_bia_v4         36.4%     untrained
    lora_tazz_v4        37.0%     untrained

I padded every frame to a square on white to avoid stretching and distorting
proportions. That filled ~a third of each training image with blank canvas and
shrank the subject, so capacity went into learning white borders.

lora_keth also proves squaring was never required: it holds 1024x1024 frames
ALONGSIDE tight panels like 365x493 and 237x493, mixed aspect ratios, no padding.
The trainer buckets them.

METHOD: crop away the uniform white border (bounding box of non-white pixels),
then scale so the LONG edge is at most MAX_EDGE, preserving aspect ratio.
Captions untouched.

Backs up originals to <folder>/_padded_backup/ so it is reversible.
Dry run by default; --write commits.
"""
import argparse
import pathlib
import shutil

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

ROOT = pathlib.Path(__file__).resolve().parents[1] / "tools" / "ComfyUI" / "input"
MAX_EDGE = 1024
WHITE = 247


def content_box(im):
    a = np.asarray(im.convert("L"))
    mask = a < WHITE
    if not mask.any():
        return None
    rows, cols = np.where(mask.any(axis=1))[0], np.where(mask.any(axis=0))[0]
    return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1


def process(path, write):
    im = Image.open(path)
    before = im.size
    box = content_box(im)
    if box:
        im = im.crop(box)
    w, h = im.size
    scale = min(1.0, MAX_EDGE / max(w, h))
    if scale < 1.0:
        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    if write:
        im.convert("RGB").save(path)
    return before, im.size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folders", nargs="+")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    for name in args.folders:
        d = ROOT / name
        if not d.is_dir():
            print(f"{name}: NOT FOUND")
            continue
        pngs = sorted(d.glob("*.png"))
        if args.write:
            bak = d / "_padded_backup"
            bak.mkdir(exist_ok=True)
            for f in pngs:
                if not (bak / f.name).exists():
                    shutil.copy2(f, bak / f.name)
        whites_before, whites_after, shapes = [], [], set()
        for f in pngs:
            a = np.asarray(Image.open(f).convert("L"))
            whites_before.append((a > WHITE).mean() * 100)
            _b, after = process(f, args.write)
            shapes.add(after)
            if args.write:
                a2 = np.asarray(Image.open(f).convert("L"))
                whites_after.append((a2 > WHITE).mean() * 100)
        mb = sum(whites_before) / max(1, len(whites_before))
        ma = (sum(whites_after) / max(1, len(whites_after))) if whites_after else None
        print("%-16s %3d imgs  white %.1f%%%s  shapes now: %s"
              % (name, len(pngs), mb,
                 f" -> {ma:.1f}%" if ma is not None else " (dry run)",
                 f"{len(shapes)} varied" if len(shapes) > 3 else list(shapes)))
    print("\n" + ("WRITTEN (originals in <folder>/_padded_backup/)" if args.write
                  else "DRY RUN -- use --write"))


if __name__ == "__main__":
    main()
