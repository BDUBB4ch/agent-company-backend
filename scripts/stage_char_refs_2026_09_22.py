"""Stage Barry's 2026-09-20 character renders as the live restage references.

Barry, 2026-09-22: "make sure elliot and the qwen image ... has it."

Every pick below was made by OPENING the frames (contact sheets + native
checks), not from filenames. The live slot the restage door reads is
tools/ComfyUI/input/char_ref_<key>.png (comfy_image.CHARACTER_REFS); it gets
the FRONT plate at 1328 long edge, the convention every existing ref uses.
The face / three-quarter / back plates have no live slot yet -- the door
takes one reference per character -- so they are staged beside it in
data/char_refs_2026-09-20/staged/<key>/ and named, ready for a multi-angle
door if Barry wants one built.

⚠️ VOR'SHARA'S LIVE REF IS DELIBERATELY NOT REPLACED. Her new plates are
NUDE, made for the lagoon scene. The restage editor carries the reference's
wardrobe into every shot and will not remove clothing it sees -- so a nude
default would make every Vor'Shara shot start nude unless the gown is
prompted back in. They are staged as char_ref_vorshara_nude.png /
_nude_back.png for that scene; her gowned ref stays the default. His call to
flip it.

Every replaced file is backed up first. Re-runnable.
"""
import os
import shutil
import sys
from datetime import datetime

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "char_refs_2026-09-20", "raw")
STAGED = os.path.join(ROOT, "data", "char_refs_2026-09-20", "staged")
INPUT = os.path.join(ROOT, "tools", "ComfyUI", "input")
BACKUP = os.path.join(INPUT, "_char_refs_backup_2026-09-22")
LONG_EDGE = 1328

# key -> (raw folder, {view: filename stem})   -- stems are the hf_ timestamp
PICKS = {
    "bdubb": ("B_Dubb_with_gun", {
        "face": "083921", "front": "085425", "threequarter": "090601", "back": "085806"}),
    "bia": ("Bia_with_gun", {
        "face": "102200", "front": "100143", "threequarter": "100955", "back": "102440"}),
    "yannah": ("Yanna_with_Gun", {
        "face": "104218", "front": "105040", "threequarter": "105214", "back": "110055"}),
    "tazz": ("Tazz_with_weapon", {
        "face": "183545", "front": "191403", "threequarter": "193211", "back": "201614"}),
    "vorshara": ("Lady_Vor_naked", {
        "front_nude": "204458", "back_nude": "204412"}),
}
# which staged view becomes the live char_ref_<key>.png
LIVE_VIEW = {"bdubb": "front", "bia": "front", "yannah": "front", "tazz": "front"}
# MyStudio's character buttons (Desktop/MyStudio.html) load char_<key>_face /
# _body from the input root. _group is a hand-cut tight body crop capped at
# 1024 (the 08-22 group-shot fix) -- left alone, it is not a plain resize.
# Keth has no new plates; Vor'Shara's are nude and stay out of her buttons.
MYSTUDIO = {
    "bdubb":  {"char_bdubb_face.png": "face",  "char_bdubb_body.png": "front"},
    "bia":    {"char_bia_face.png": "face",    "char_bia_body.png": "front"},
    "yannah": {"char_yannah_face.png": "face", "char_yannah_body.png": "front"},
    "tazz":   {"char_tazz_face.png": "face",   "char_tazz_body.png": "front"},
}


def find(folder, stem):
    hits = [f for f in os.listdir(os.path.join(RAW, folder)) if stem in f]
    assert len(hits) == 1, f"{folder}/{stem}: expected 1 file, got {hits}"
    return os.path.join(RAW, folder, hits[0])


def fit(src, dst, long_edge=LONG_EDGE):
    im = Image.open(src).convert("RGB")
    w, h = im.size
    if max(w, h) != long_edge:
        s = long_edge / max(w, h)
        im = im.resize((round(w * s), round(h * s)), Image.LANCZOS)
    im.save(dst, "PNG")
    return im.size


def backup(path):
    if os.path.exists(path):
        os.makedirs(BACKUP, exist_ok=True)
        dst = os.path.join(BACKUP, os.path.basename(path))
        if not os.path.exists(dst):
            shutil.copy2(path, dst)
            return True
    return False


def main() -> int:
    print(f"staging  -> {STAGED}")
    print(f"live     -> {INPUT}")
    print(f"backups  -> {BACKUP}\n")

    for key, (folder, views) in PICKS.items():
        os.makedirs(os.path.join(STAGED, key), exist_ok=True)
        for view, stem in views.items():
            src = find(folder, stem)
            dst = os.path.join(STAGED, key, f"{view}.png")
            size = fit(src, dst)
            print(f"  {key:<9} {view:<13} {size[0]}x{size[1]}  <- {os.path.basename(src)[3:18]}")

        if key in LIVE_VIEW:
            live = os.path.join(INPUT, f"char_ref_{key}.png")
            b = backup(live)
            shutil.copy2(os.path.join(STAGED, key, f"{LIVE_VIEW[key]}.png"), live)
            # the 16:9 padded twin is rebuilt by comfy_image._wide_reference when
            # the source is newer; remove the stale one so it cannot be served
            wide = os.path.join(INPUT, f"char_ref_{key}_wide.png")
            if os.path.exists(wide):
                backup(wide)
                os.remove(wide)
            print(f"  {key:<9} LIVE char_ref_{key}.png replaced"
                  f"{' (old backed up)' if b else ''}, _wide removed for rebuild")
        else:
            # explicit names for her two plates; the gowned default is untouched
            for view, name in (("front_nude", "char_ref_vorshara_nude.png"),
                               ("back_nude", "char_ref_vorshara_nude_back.png")):
                live = os.path.join(INPUT, name)
                backup(live)
                shutil.copy2(os.path.join(STAGED, key, f"{view}.png"), live)
                print(f"  {key:<9} staged {name} (gowned default NOT replaced)")

        for name, view in MYSTUDIO.get(key, {}).items():
            live = os.path.join(INPUT, name)
            b = backup(live)
            shutil.copy2(os.path.join(STAGED, key, f"{view}.png"), live)
            print(f"  {key:<9} MyStudio {name} <- {view}{' (old backed up)' if b else ''}")
        print()

    # touch the live files so any mtime-based cache sees them as new
    now = datetime.now().timestamp()
    for f in os.listdir(INPUT):
        if f.startswith("char_ref_") or f.startswith("char_bia_"):
            os.utime(os.path.join(INPUT, f), (now, now))

    print("done. live refs now:")
    for f in sorted(os.listdir(INPUT)):
        if f.startswith("char_ref_") and not f.endswith("_wide.png"):
            im = Image.open(os.path.join(INPUT, f))
            print(f"  {f:<34} {im.size[0]}x{im.size[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
