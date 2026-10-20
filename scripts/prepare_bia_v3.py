"""Build lora_bia_v3 from the audited set (2026-08-05).

Audit: data/bia_dataset_audit_2026-08-05.txt — every one of the 49 frames was
opened. 7 whole multi-panel sheets EXCLUDED (they taught the grid habit that
ruined Bia's renders; they stay untouched in lora_bia for a proper eyeballed
split later). 5 bleed-edge frames get the contaminated edge cropped off.
Everything else copies as-is. COPY only; lora_bia is never modified.

Run with --preview first: writes the trimmed frames to _preview so the crops
can be EYEBALLED before committing (auto-anything on sheets is banned).
"""
import argparse
import shutil
from pathlib import Path

from PIL import Image

SRC = Path(__file__).resolve().parent.parent / "tools" / "ComfyUI" / "input"
BIA = SRC / "lora_bia"
DEST = SRC / "lora_bia_v3"

SHEETS = {"000", "001", "033", "034", "036", "038", "066"}
# stem -> (left, top, right, bottom) as fractions of the full image to KEEP.
# The sliver sits at the content edge; these cuts were sized from the audit
# views and MUST be previewed before --write.
BLEED_TRIM = {
    "004": (0.0, 0.0, 1.0, 0.84),   # second figure bottom band
    "005": (0.0, 0.0, 1.0, 0.86),   # head sliver bottom edge
    "006": (0.0, 0.0, 1.0, 0.82),   # head sliver bottom edge
    "008": (0.0, 0.0, 1.0, 0.86),   # sliver bottom
    "009": (0.0, 0.0, 0.62, 1.0),   # second figure right edge (0.88 and 0.78 both left arm fragments)
}
# Honest style captions (the Humboldt-cap lesson): these two are drawn
# illustration artwork, and saying so keeps the style promptable so only
# the character binds to @Bia.
ILLUSTRATION = {"041", "043"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="build lora_bia_v3 (default: preview trims only)")
    args = ap.parse_args()

    out = DEST if args.write else SRC / "lora_bia_v3_preview"
    out.mkdir(exist_ok=True)

    copied = trimmed = 0
    for png in sorted(BIA.glob("*.png")):
        stem = png.stem
        base = stem.split("_")[0]
        if base in SHEETS:
            continue
        txt = png.with_suffix(".txt")
        caption = txt.read_text(encoding="utf-8") if txt.exists() else ""
        if base in ILLUSTRATION and "illustration" not in caption.lower():
            caption = caption.rstrip() + ", digital illustration artwork style"
        if base in BLEED_TRIM:
            l, t, r, b = BLEED_TRIM[base]
            im = Image.open(png)
            w, h = im.size
            im.crop((int(l * w), int(t * h), int(r * w), int(b * h))).save(
                out / png.name)
            trimmed += 1
        elif args.write:
            shutil.copy2(png, out / png.name)
            copied += 1
        if args.write:
            (out / (stem + ".txt")).write_text(caption, encoding="utf-8")
    print(f"{'wrote' if args.write else 'PREVIEW'}: {copied} copied, "
          f"{trimmed} trimmed -> {out}")
    if args.write:
        n = len(list(out.glob("*.png")))
        print(f"total frames: {n}")


if __name__ == "__main__":
    main()
