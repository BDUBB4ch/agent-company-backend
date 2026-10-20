"""Round 2 of the 2026-09-22 reference staging.

The three zips arrived MISLABELLED (checked by opening every frame):
  "more tazz.zip"          -> BIA, 8 plates at 1728x2304
  "More Bia.zip"           -> YANNAH, 4 plates at 1728x2304 (the face he prefers)
  "Better Yannah Face.zip" -> the Tazz set from round 1, byte-for-byte; nothing new

Upgrades only where the new plate is genuinely better (hi-res, same canon).
Bia's front + back go hi-res; Yannah's face becomes the one he prefers, cropped
from her head sheet; her 3/4 full goes hi-res. Everything replaced is backed up.
"""
import os
import shutil

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "char_refs_2026-09-20", "raw")
STAGED = os.path.join(ROOT, "data", "char_refs_2026-09-20", "staged")
INPUT = os.path.join(ROOT, "tools", "ComfyUI", "input")
BACKUP = os.path.join(INPUT, "_char_refs_backup_2026-09-22")
LONG = 1328


def find(folder, stem):
    hits = [f for f in os.listdir(os.path.join(RAW, folder)) if stem in f]
    assert len(hits) == 1, f"{folder}/{stem}: {hits}"
    return os.path.join(RAW, folder, hits[0])


def fit(im, long_edge=LONG):
    w, h = im.size
    if max(w, h) != long_edge:
        s = long_edge / max(w, h)
        im = im.resize((round(w * s), round(h * s)), Image.LANCZOS)
    return im


def backup(path):
    if os.path.exists(path):
        os.makedirs(BACKUP, exist_ok=True)
        dst = os.path.join(BACKUP, os.path.basename(path))
        if not os.path.exists(dst):
            shutil.copy2(path, dst)


def stage(key, view, src_img, live_names=()):
    dst = os.path.join(STAGED, key, f"{view}.png")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst):
        prev = os.path.join(STAGED, key, f"{view}_round1.png")
        if not os.path.exists(prev):
            shutil.move(dst, prev)
    im = fit(src_img.convert("RGB"))
    im.save(dst, "PNG")
    for name in live_names:
        live = os.path.join(INPUT, name)
        backup(live)
        im.save(live, "PNG")
    print(f"  {key:<7} {view:<16} {im.size[0]}x{im.size[1]}"
          + (f"  -> LIVE {', '.join(live_names)}" if live_names else ""))


# ------------------------------------------------------------------ BIA ----
print("BIA (from 'more tazz.zip')")
stage("bia", "front", Image.open(find("more_tazz", "075216")),
      live_names=("char_ref_bia.png", "char_bia_body.png"))
stage("bia", "back", Image.open(find("more_tazz", "081855")))
stage("bia", "rear_threequarter", Image.open(find("more_tazz", "081229")))
stage("bia", "front_alt", Image.open(find("more_tazz", "075959")))
stage("bia", "head_sheet", Image.open(find("more_tazz", "073306")))
wide = os.path.join(INPUT, "char_ref_bia_wide.png")
if os.path.exists(wide):
    backup(wide); os.remove(wide)
# face: the round-1 tight straight-on close-up (102200) stays -- the new head
# sheet is 1376x768 with ~460px heads, smaller than what is already staged.

# --------------------------------------------------------------- YANNAH ----
print("\nYANNAH (from 'More Bia.zip')")
sheet = Image.open(find("More_Bia", "083402"))          # 1728x2304 head sheet
w, h = sheet.size
face = sheet.crop((0, 0, w // 2 + 40, int(h * 0.52)))    # top-left panel: 3/4 front head
stage("yannah", "face", face, live_names=("char_yannah_face.png",))
stage("yannah", "head_sheet", sheet)
stage("yannah", "threequarter", Image.open(find("More_Bia", "083151")))
stage("yannah", "turnaround", Image.open(find("More_Bia", "083751")))
stage("yannah", "poses", Image.open(find("More_Bia", "084237")))
# live char_ref_yannah (single front, 105040) stays: the new front only exists
# inside the 3-panel turnaround, and the restage door needs one figure.

print("\nTAZZ: 'Better Yannah Face.zip' == round-1 Tazz set, nothing staged.")
print("\ncheck the Yannah face crop:", os.path.join(STAGED, "yannah", "face.png"))
