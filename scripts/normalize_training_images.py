"""Normalise a LoRA training folder to 1024x1024, the size SDXL actually trains at.

WHY THIS EXISTS (2026-08-07/08 post-mortem):
The v4 sets were built by copying source frames at FULL resolution -- up to
3520x4704. Comparison against the datasets that trained successfully:

    lora_keth     (worked)  41 imgs   12.9 MPx total   largest 1024x1024
    lora_keth_v4  (failed)  55 imgs  182.3 MPx total   largest 3520x4704

14x the pixel volume. ComfyUI could not fit the latent cache, logged
"0.00 MB usable" and offloaded 1.5GB to system RAM over and over, training
ran at 13.45 s/step instead of ~5.5, blew the 12h timeout, and the pinned
memory pressure (19.5GB pinned of 48GB) froze the desktop.

SDXL trains at 1024. The extra resolution bought nothing.

Method: pad to square on WHITE (never stretch -- stretching distorts body
proportions, and for Keth the ~4ft proportion is the whole point), then
resize to 1024x1024 with LANCZOS. Captions are left untouched.

Run:  ../venv/Scripts/python.exe scripts/normalize_training_images.py lora_keth_v4 [more...]
      add --dry-run to just report
"""
import argparse
import pathlib
import sys

from PIL import Image

Image.MAX_IMAGE_PIXELS = None

SIZE = 1024
ROOT = pathlib.Path(__file__).resolve().parents[1] / "tools" / "ComfyUI" / "input"


def normalise(path: pathlib.Path) -> tuple[tuple[int, int], tuple[int, int]]:
    im = Image.open(path)
    before = im.size
    if before == (SIZE, SIZE):
        return before, before
    side = max(im.size)
    canvas = Image.new("RGB", (side, side), (255, 255, 255))
    canvas.paste(im.convert("RGB"), ((side - im.width) // 2, (side - im.height) // 2))
    canvas.resize((SIZE, SIZE), Image.LANCZOS).save(path)
    return before, (SIZE, SIZE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folders", nargs="+")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    for name in args.folders:
        d = ROOT / name
        if not d.is_dir():
            print(f"{name}: NOT FOUND", file=sys.stderr)
            continue
        files = sorted(d.glob("*.png"))
        before_px = sum(Image.open(f).size[0] * Image.open(f).size[1] for f in files)
        if args.dry_run:
            over = sum(1 for f in files
                       if Image.open(f).size[0] * Image.open(f).size[1] > SIZE * SIZE)
            print("%-16s %3d imgs  %7.1f MPx  ->  %5.1f MPx   (%d need resizing)"
                  % (name, len(files), before_px / 1e6, len(files) * SIZE * SIZE / 1e6, over))
            continue
        changed = 0
        for f in files:
            b, a = normalise(f)
            if b != a:
                changed += 1
        after_px = len(files) * SIZE * SIZE
        print("%-16s %3d imgs  %7.1f MPx -> %5.1f MPx   (%d resized)"
              % (name, len(files), before_px / 1e6, after_px / 1e6, changed))


if __name__ == "__main__":
    main()
