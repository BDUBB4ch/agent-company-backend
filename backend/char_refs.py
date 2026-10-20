"""
char_refs.py -- give the character engine more pictures without code (2026-09-22).

Barry: "Make sure there is a way to give elliot or the qwen thing more images if
we need to." Until now a new angle of Keth meant Claude hand-staging a file into
ComfyUI's input folder and rebuilding that character's reference sheet with a
throwaway script. This is the door instead:

    drop/Characters/<Name>/<view>/  <- drop any picture here

<Name> is BDubb, Bia, Tazz, Yannah, Vorshara or Keth. <view> is one of the
folders below. Within about a minute (the same 60s loop that runs the TEACH DROP
folders) the picture is staged where comfy_image.py already looks, the old file
it replaces is backed up, and the character's all-angles sheet
(char_<key>_sheet.png -- what Qwen-Image 2.1 actually receives) is rebuilt. The
original moves to drop/Characters/_done/. Nothing else changes: no restart, no
code edit, and the next @handle render uses it.

Staging targets (all in <COMFY_DIR>/input):
    face              -> char_<key>_face.png          (front face close-up)
    front             -> char_ref_<key>.png           (THE MAIN REFERENCE, whole figure)
    props             -> char_<key>_prop_<name>.png   (things they always WEAR)
    anything else     -> char_<key>_angle_<view>.png

No model calls, no GPU -- PIL only, so it can run mid-render.
"""
from __future__ import annotations

import os
import re
import shutil
from datetime import datetime

from config import COMFY_DIR

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DROP = os.path.join(_ROOT, "drop", "Characters")
INPUT = os.path.join(COMFY_DIR, "input")
BACKUP = os.path.join(INPUT, "_char_refs_backup_dropdoor")

CHARACTERS = {"BDubb": "bdubb", "Bia": "bia", "Tazz": "tazz",
              "Yannah": "yannah", "Vorshara": "vorshara", "Keth": "keth"}
# Sheet panel order after face + front. Must match comfy_image._ANGLE_VIEWS names.
ANGLE_VIEWS = ["threequarter", "side", "rear_threequarter", "back",
               "front_nude", "back_nude"]
VIEWS = ["face", "front"] + ANGLE_VIEWS + ["props"]
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

REF_LONG_EDGE = 1328          # the staging convention for every char_ref
SHEET_PANEL_H = 700           # matches the sheets built 2026-09-22
SHEET_PAD = 24
SHEET_GREY = (128, 128, 128)

_README = """DROP PICTURES HERE TO GIVE THE CHARACTER ENGINE MORE TO WORK FROM

Pick the character folder, then the folder that says what the picture shows:
  face               a front close-up of the face
  front              the whole figure from the front -- REPLACES their main reference
  threequarter       whole figure at a three-quarter angle
  side               side profile
  rear_threequarter  from behind at three-quarters
  back               straight from behind
  front_nude / back_nude   undressed views
  props              things they ALWAYS WEAR (cap, pendant, ear cuff) -- never weapons

Within about a minute the office stages it, backs up whatever it replaced, and
rebuilds that character's all-angles sheet. The original moves to _done.
One picture per view folder at a time; a newer drop replaces the older one.
"""


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def ensure_tree() -> None:
    for name in CHARACTERS:
        for view in VIEWS:
            os.makedirs(os.path.join(DROP, name, view), exist_ok=True)
    os.makedirs(os.path.join(DROP, "_done"), exist_ok=True)
    os.makedirs(os.path.join(DROP, "_failed"), exist_ok=True)
    readme = os.path.join(DROP, "README.txt")
    if not os.path.isfile(readme):
        with open(readme, "w", encoding="utf-8") as f:
            f.write(_README)


def _backup(path: str) -> None:
    if os.path.isfile(path):
        os.makedirs(BACKUP, exist_ok=True)
        stem, ext = os.path.splitext(os.path.basename(path))
        shutil.copy2(path, os.path.join(BACKUP, f"{stem}_{_stamp()}{ext}"))


def _target(key: str, view: str, src_name: str) -> str:
    if view == "face":
        return f"char_{key}_face.png"
    if view == "front":
        return f"char_ref_{key}.png"
    if view == "props":
        slug = re.sub(r"[^a-z0-9]+", "_", os.path.splitext(src_name)[0].lower()).strip("_")
        return f"char_{key}_prop_{slug or 'item'}.png"
    return f"char_{key}_angle_{view}.png"


def _stage(src: str, dst_name: str) -> str:
    from PIL import Image
    dst = os.path.join(INPUT, dst_name)
    with Image.open(src) as im:
        im = im.convert("RGB")
        if max(im.size) > REF_LONG_EDGE:
            s = REF_LONG_EDGE / float(max(im.size))
            im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
        _backup(dst)
        tmp = dst + ".tmp.png"
        im.save(tmp)
    os.replace(tmp, dst)
    return dst


def _sheet_panels(key: str) -> list[str]:
    def have(n: str) -> str | None:
        p = os.path.join(INPUT, n)
        return p if os.path.isfile(p) else None
    panels = [have(f"char_{key}_face.png"),
              have(f"char_{key}_angle_front.png") or have(f"char_ref_{key}.png")]
    panels += [have(f"char_{key}_angle_{v}.png") for v in ANGLE_VIEWS]
    props = sorted(n for n in os.listdir(INPUT)
                   if n.startswith(f"char_{key}_prop_") and n.endswith(".png")
                   and not re.search(r"_s\d+\.png$|_small\.png$|_wide\.png$", n))
    panels += [os.path.join(INPUT, n) for n in props]
    return [p for p in panels if p]


def rebuild_sheet(key: str) -> str | None:
    """Every staged view of one character side by side on grey, 700px tall."""
    from PIL import Image
    panels = _sheet_panels(key)
    if not panels:
        return None
    ims = []
    for p in panels:
        with Image.open(p) as im:
            im = im.convert("RGB")
            s = SHEET_PANEL_H / float(im.height)
            ims.append(im.resize((max(1, round(im.width * s)), SHEET_PANEL_H), Image.LANCZOS))
    w = SHEET_PAD + sum(i.width + SHEET_PAD for i in ims)
    sheet = Image.new("RGB", (w, SHEET_PANEL_H + 2 * SHEET_PAD), SHEET_GREY)
    x = SHEET_PAD
    for i in ims:
        sheet.paste(i, (x, SHEET_PAD))
        x += i.width + SHEET_PAD
    dst = os.path.join(INPUT, f"char_{key}_sheet.png")
    _backup(dst)
    tmp = dst + ".tmp.png"
    sheet.save(tmp)
    os.replace(tmp, dst)
    return dst


def scan() -> list[str]:
    """One pass. Never raises. Returns receipts."""
    receipts: list[str] = []
    try:
        ensure_tree()
    except Exception as e:  # noqa: BLE001
        return [f"[char-refs] could not create drop folders: {e}"]
    touched: set[str] = set()
    for name, key in CHARACTERS.items():
        for view in VIEWS:
            folder = os.path.join(DROP, name, view)
            try:
                files = sorted(os.listdir(folder),
                               key=lambda f: os.path.getmtime(os.path.join(folder, f)))
            except OSError:
                continue
            for fn in files:
                src = os.path.join(folder, fn)
                if not os.path.isfile(src) or os.path.splitext(fn)[1].lower() not in IMAGE_EXTS:
                    continue
                stamp = _stamp()
                try:
                    dst = _stage(src, _target(key, view, fn))
                    shutil.move(src, os.path.join(DROP, "_done", f"{stamp}_{name}_{view}_{fn}"))
                    touched.add(key)
                    receipts.append(f"[char-refs] {name}/{view}: {fn} -> {os.path.basename(dst)}")
                except Exception as e:  # noqa: BLE001
                    try:
                        bad = os.path.join(DROP, "_failed", f"{stamp}_{name}_{view}_{fn}")
                        shutil.move(src, bad)
                        with open(bad + ".why.txt", "w", encoding="utf-8") as f:
                            f.write(f"{type(e).__name__}: {e}\n")
                    except Exception:  # noqa: BLE001
                        pass
                    receipts.append(f"[char-refs] FAILED {name}/{view}/{fn}: {e}")
    for key in sorted(touched):
        try:
            p = rebuild_sheet(key)
            receipts.append(f"[char-refs] sheet rebuilt: {os.path.basename(p) if p else 'no panels'}")
        except Exception as e:  # noqa: BLE001
            receipts.append(f"[char-refs] sheet rebuild FAILED for {key}: {e}")
    for r in receipts:
        print(r, flush=True)
    return receipts
