"""Training sets for Yannah and Ilnora (Barry 2026-09-25: "train them all"), from his Higgsfield pictures.
Rules (LoRA training folder rule): ONE person per frame, no text overlays, every frame 768x1024, folder holds only
frames + captions. Multi-view sheets are cut into single views. Caption = trigger + view.
    venv/Scripts/python.exe scripts/zimage_datasets_2026_09_25.py
"""
import glob
import os
import shutil

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INP = r"D:\ComfyUI25\input"
Y = os.path.join(ROOT, "data", "higgs_zips_2026_09_24", "archive_14_yannah")
R = os.path.join(ROOT, "data", "higgs_zips_2026_09_24", "refs")
L = os.path.join(ROOT, "data", "identity", "ilnora", "library")


def fit(im, cx=0.5):
    """3:4 window (768x1024) around horizontal centre cx."""
    im = im.convert("RGB")
    w, h = im.size
    if w / h > 0.75:
        cw = int(h * 0.75)
        left = min(max(0, int(cx * w) - cw // 2), w - cw)
        im = im.crop((left, 0, left + cw, h))
    elif w / h < 0.74:
        # tall full-body frames: PAD the sides with the picture's own edge colour -- never crop off the legs
        # (a "full body" caption on a waist-up crop teaches the wrong thing)
        px = [im.getpixel((x, y)) for x in (0, w - 1) for y in range(0, h, max(1, h // 40))]
        fill = tuple(sorted(c[k] for c in px)[len(px) // 2] for k in range(3))
        nw = int(h * 0.75)
        canvas = Image.new("RGB", (nw, h), fill)
        canvas.paste(im, ((nw - w) // 2, 0))
        im = canvas
    return im.resize((768, 1024), Image.LANCZOS)


def panels(path, n):
    im = Image.open(path).convert("RGB")
    w = im.width / n
    return [im.crop((int(i * w), 0, int((i + 1) * w), im.height)) for i in range(n)]


def build(folder, trigger, items):
    d = os.path.join(INP, folder)
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(d)
    for i, (im, view) in enumerate(items):
        name = f"{i:03d}"
        fit(im).save(os.path.join(d, name + ".png"))
        with open(os.path.join(d, name + ".txt"), "w", encoding="utf-8") as fh:
            fh.write(f"{trigger}, {view}")
    print(folder, len(items), "frames")


def y(i):
    return Image.open(glob.glob(os.path.join(Y, f"{i:02d}_*.png"))[0])


# YANNAH -- archive (14): 2 and 3 carry text overlays (left out); 4 is a face + two small heads (face panel only);
# 6/7/8 are turnarounds (cut into single views); 5 and 12 fire a green flash, not her canon rounds -- the gun is
# not what is being learned, so they stay as body/pose frames. Plus Barry's two full-body pictures.
yannah = [
    (y(0), "upper body, front, aiming a pistol"), (y(1), "upper body, front, aiming a pistol"),
    (Image.open(glob.glob(os.path.join(Y, "04_*.png"))[0]).crop((0, 0, 768, 700)), "face close-up, front"),
    (y(5), "upper body, three-quarter view"), (y(9), "full body, back view"), (y(10), "full body, back view"),
    (y(11), "face close-up, three-quarter view"), (y(12), "full body, back view"), (y(13), "full body, kneeling"),
    (Image.open(os.path.join(R, "yannah_body_barry_gun_in_hand.png")), "full body, front"),
]
for i, (p, views) in enumerate([(glob.glob(os.path.join(Y, "06_*.png"))[0], ["full body, front", "full body, back view",
                                  "full body, three-quarter view", "full body, side view"]),
                                 (glob.glob(os.path.join(Y, "07_*.png"))[0], ["full body, front", "full body, back view",
                                  "full body, three-quarter view"]),
                                 (os.path.join(R, "yannah_sheet_holstered_barry.png"), ["full body, front",
                                  "full body, back view", "full body, three-quarter view"])]):
    for panel, view in zip(panels(p, len(views)), views):
        yannah.append((panel, view))
build("lora_yannah_zimage", "@yannah", yannah)

# ILNORA -- her 27-picture library (archive 13), all single-subject, no text.
IL_VIEWS = {0: "face close-up, front", 1: "upper body, grinding herbs", 2: "upper body, pouring tea",
            3: "upper body, holding herbs", 4: "upper body, stirring a pot", 5: "upper body, holding a bottle",
            6: "upper body, writing", 7: "upper body, writing", 8: "full body, garden gate",
            9: "full body, forest path", 10: "full body, herb garden at dusk", 11: "full body, apothecary",
            12: "full body, moonlit lane with a lantern", 13: "full body, black cloak by a bonfire",
            14: "upper body, harvesting herbs in an apron", 15: "upper body, holding a jack-o-lantern",
            16: "full body, graveyard with a raven", 17: "upper body, holding a bottle to the light",
            18: "upper body, tying herbs", 19: "upper body, reading with glasses", 20: "upper body, front portrait",
            21: "face close-up, front", 22: "upper body, laughing", 23: "upper body, three-quarter view",
            24: "upper body, seated at a table", 25: "upper body, gathering herbs in a meadow",
            26: "upper body, holding a basket in a meadow"}
IL_CX = {24: 0.78, 25: 0.62, 26: 0.72}      # wide frames: where she stands (the table shot has her at the right)
pics = sorted(glob.glob(os.path.join(L, "*.png")))
ilnora = []
for p in pics:
    i = int(os.path.basename(p)[:2])
    im = Image.open(p)
    if i in IL_CX:
        im = fit(im, IL_CX[i])
    ilnora.append((im, IL_VIEWS.get(i, "photo")))
build("lora_ilnora_zimage", "@ilnora", ilnora)
