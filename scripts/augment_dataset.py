"""Stretch a thin character set with real variation (2026-08-05).

Barry's question: why not reuse duplicate images as new images? Because
duplicates add WEIGHT, not information -- a repeated front shot never teaches
a profile. Mirroring does add information: it gives the model the other side
of every pose it has, which is standard LoRA augmentation.

Writes <folder>_aug containing the originals PLUS a mirrored copy of each
eligible frame. Originals are never modified.

MIRRORING IS NOT SAFE FOR EVERY CHARACTER. Anything with a sided identity
feature learns a lie when flipped:
  - bia   : faded pixie is SHAVED ON ONE SIDE -> never mirror
  - bdubb : cap star sits on one side, plus he is a real person -> never mirror
  - keth  : canon notes no sided feature, but his set is mostly drawn panels
            with baked-in layout -> mirror only the photoreal singles
  - tazz  : twin braids, symmetric face. The diagonal chest strap flips, but
            gear is not identity and her captions describe it generically.
  - yannah: gold freckle SPOTS may be placed asymmetrically -> off by default
Pass --allow-mirror to override for a folder not in the safe list.
"""
import argparse
import shutil
from pathlib import Path

from PIL import Image, ImageOps

INPUT = Path(__file__).resolve().parent.parent / "tools" / "ComfyUI" / "input"
MIRROR_SAFE = {"lora_tazz", "lora_vorshara", "lora_vorshara_v4"}
NEVER_MIRROR = {"lora_bia", "lora_bia_v3", "lora_bdubb"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", help="e.g. lora_tazz")
    ap.add_argument("--allow-mirror", action="store_true",
                    help="force mirroring for a folder not on the safe list")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    src = INPUT / args.folder
    if not src.is_dir():
        raise SystemExit(f"no such folder: {src}")
    if args.folder in NEVER_MIRROR and not args.allow_mirror:
        raise SystemExit(
            f"{args.folder} has a sided identity feature -- mirroring would "
            "teach it backwards. Override with --allow-mirror only if you have "
            "checked every frame.")
    if args.folder not in MIRROR_SAFE and not args.allow_mirror:
        raise SystemExit(f"{args.folder} is not on the mirror-safe list; "
                         "pass --allow-mirror if you have verified it.")

    dst = INPUT / f"{args.folder}_aug"
    pngs = sorted(src.glob("*.png"))
    if not args.write:
        print(f"PREVIEW: {len(pngs)} originals + {len(pngs)} mirrors "
              f"= {len(pngs) * 2} frames -> {dst}")
        return

    dst.mkdir(exist_ok=True)
    for png in pngs:
        txt = png.with_suffix(".txt")
        caption = txt.read_text(encoding="utf-8").strip() if txt.exists() else ""
        shutil.copy2(png, dst / png.name)
        (dst / txt.name).write_text(caption, encoding="utf-8")
        # mirrored twin -- same caption, the character is the same person
        ImageOps.mirror(Image.open(png)).save(dst / f"{png.stem}_mir.png")
        (dst / f"{png.stem}_mir.txt").write_text(caption, encoding="utf-8")
    n = len(list(dst.glob("*.png")))
    print(f"wrote {n} frames -> {dst}")


if __name__ == "__main__":
    main()
