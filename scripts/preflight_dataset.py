"""Refuse to train on a dataset that will thrash VRAM. Exit 1 = do not train.

Written after the 2026-08-07 failure: lora_keth_v4 carried full-resolution frames
(largest 3520x4704, 182.3 MPx total) against the 12.9 MPx of lora_keth, which had
trained fine. ComfyUI logged "0.00 MB usable", offloaded 1.5GB to system RAM on
repeat, trained at 13.45 s/step instead of ~5.5, blew the 12h timeout, and the
pinned-memory pressure froze the desktop.

Checks:
  - every image is exactly 1024x1024 (what SDXL trains at)
  - a caption exists and is non-trivial for every image
  - total pixel volume is sane
"""
import pathlib
import sys

from PIL import Image

Image.MAX_IMAGE_PIXELS = None

SIZE = 1024
MAX_TOTAL_MPX = 120.0
MAX_WHITE_PCT = 12.0   # lora_keth 0.3, lora_vorshara 0.1, lora_bdubb 6.7 -- all worked.
                       # keth_v5 at 28.5% learned essentially nothing.
ROOT = pathlib.Path(__file__).resolve().parents[1] / "tools" / "ComfyUI" / "input"


def main():
    if len(sys.argv) < 2:
        print("usage: preflight_dataset.py <folder>")
        return 1
    d = ROOT / sys.argv[1]
    if not d.is_dir():
        print(f"PRE-FLIGHT FAIL: {d} does not exist")
        return 1

    pngs = sorted(d.glob("*.png"))
    if not pngs:
        print(f"PRE-FLIGHT FAIL: no images in {d}")
        return 1

    bad_size, no_cap, total, whites = [], [], 0, []
    for f in pngs:
        im = Image.open(f)
        w, h = im.size
        total += w * h
        # Square is NOT required -- lora_keth mixes 1024x1024 with 365x493 panels
        # and trained fine. What matters is that no single frame is huge.
        if max(w, h) > SIZE:
            bad_size.append(f"{f.name} {w}x{h}")
        import numpy as _np
        whites.append((_np.asarray(im.convert("L")) > 247).mean() * 100)
        cap = f.with_suffix(".txt")
        if not cap.exists() or len(cap.read_text(encoding="utf-8").strip()) < 20:
            no_cap.append(f.name)

    mpx = total / 1e6
    print(f"  {len(pngs)} images, {mpx:.1f} MPx total")

    fail = False
    mean_white = sum(whites) / max(1, len(whites))
    print(f"  mean blank-white area: {mean_white:.1f}%")
    if bad_size:
        print(f"  FAIL: {len(bad_size)} image(s) with an edge over {SIZE}px: {bad_size[:4]}")
        fail = True
    if mean_white > MAX_WHITE_PCT:
        print(f"  FAIL: {mean_white:.1f}% blank white exceeds {MAX_WHITE_PCT}% "
              f"-- padding starves training. Run depad_training_images.py")
        fail = True
    if no_cap:
        print(f"  FAIL: {len(no_cap)} image(s) missing or trivial caption: {no_cap[:4]}")
        fail = True
    if mpx > MAX_TOTAL_MPX:
        print(f"  FAIL: {mpx:.1f} MPx exceeds the {MAX_TOTAL_MPX} MPx ceiling")
        fail = True

    if fail:
        return 1
    print("  PRE-FLIGHT OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
