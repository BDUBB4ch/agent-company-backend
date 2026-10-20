"""Stage B Dubb's Banger reference the same way the other three props are.

Pattern (set 2026-08-14): originals live in data/props/<weapon>/, and the hero
frame is converted to PNG in the ComfyUI input ROOT -- LoadImage does not list
subfolders, so a reference anywhere else is invisible to the pipeline.

Hero = the full 3/4 angle with the whole weapon in frame (_6), not the muzzle
close-up (_1). Re-runnable.
"""
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "data" / "props" / "bdubb-banger"
OUT = ROOT / "tools" / "ComfyUI" / "input" / "bdubb_banger_ref.png"

hero = next((p for p in sorted(SRC_DIR.iterdir()) if "_6" in p.name), None)
if hero is None:
    sys.exit(f"no hero frame (_6) found in {SRC_DIR}")

im = Image.open(hero).convert("RGB")
im.save(OUT, "PNG")
print(f"hero source : {hero.name}  {im.size}")
print(f"staged      : {OUT.relative_to(ROOT)}  {OUT.stat().st_size:,} bytes")

# The other three, for comparison -- a mismatch in size here means the pipeline
# will treat this reference differently from its siblings.
for name in ("bia_pistol", "yannah_pistol", "tazz_weapon", "bdubb_banger"):
    p = OUT.parent / f"{name}_ref.png"
    if p.exists():
        print(f"  {name:<14} {Image.open(p).size}")
