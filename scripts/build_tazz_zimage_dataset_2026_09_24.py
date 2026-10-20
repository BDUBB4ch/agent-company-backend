"""Tazz's Z-Image LoRA dataset (Barry, 2026-09-24). Pictures used exactly as he
rendered them -- he chose "leave it and hope it prompts in" after the Qwen-Edit
eye fix came back as cartoon bullseyes. Captions name the eyes as they appear
("violet eyes") so the colour is learned under that word, not under @Tazz, and a
prompt saying "pink and blue double-ringed irises" has room to win.

Sources, all opened first: archive (11).zip (sheets 1, 2, 4 split at cuts set by
eye on data/zimage_lora/tazz_splitguide.jpg; #9 = launcher alone, EXCLUDED), his
pasted gray full-body, and Tazz with weapon.zip (09-20). Every frame 768x1024.
"""
import glob, io, os, shutil, sys, zipfile
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from config import COMFY_DIR  # noqa: E402
from build_bdubb_zimage_dataset_2026_09_24 import to_34  # noqa: E402

SRC = os.path.join(ROOT, "data", "zimage_lora", "tazz_src")
OUT = os.path.join(COMFY_DIR, "input", "lora_tazz_zimage")
TRIG = "@Tazz, violet eyes"

PANELS = {
    "060944": [((0, 0, .28, .51), "full body, front"), ((.28, 0, .49, .51), "full body, side view, launcher on her back"),
               ((.49, 0, .73, .51), "full body, back view, launcher on her back"),
               ((.73, 0, 1, .51), "full body, looking over her shoulder, launcher on her back"),
               ((0, .53, .23, 1), "full body, holding the launcher two-handed"),
               ((.23, .53, .41, 1), "full body, holding the launcher two-handed"),
               ((.41, .53, .64, 1), "crouching, aiming the launcher"),
               ((.64, .53, 1, 1), "wide stance, aiming the launcher")],
    "060659": [((0, 0, .5, 1), "full body, front"), ((.5, 0, 1, 1), "full body, back view, launcher on her back")],
    # cuts re-measured off the guide after the first build (panels 11-13 caught
    # slivers of neighbours; the kneeling figure is dropped -- the standing
    # figures' boots overlap her head, no clean crop exists; the front-holding
    # panel dropped too -- her arm touches the edge and the kneeling head intrudes)
    "060933": [((.47, 0, .60, .66), "full body, side view"), ((.60, 0, .735, .66), "full body, three-quarter view"),
               ((.87, 0, 1, .66), "full body, back view, launcher on her back"),
               ((0, .38, .14, .93), "full body, three-quarter view"), ((.14, .38, .262, .93), "full body, side view"),
               ((.27, .38, .46, .93), "crouching, holding the launcher")],
    "060716": [((0, 0, 1, 1), "upper body, looking over her shoulder, launcher on her back")],
    "060749": [((0, 0, 1, 1), "upper body, holding the launcher two-handed")],
    "055040": [((0, 0, 1, 1), "upper body, back view, launcher on her back")],
    "052459": [((0, 0, 1, 1), "upper body, three-quarter view, launcher on her back")],
    "060223": [((0, 0, 1, 1), "full body, back view, launcher on her back")],
    "055959": [((0, 0, 1, 1), "upper body, looking over her shoulder")],
    "055038": [((0, 0, 1, 1), "face close-up, three-quarter view")],
}
OLD_ZIP = ["full body, back view, launcher on her back", "face close-up, front",
           "full body, front, launcher on her back", "full body, front, launcher on her back",
           "full body, three-quarter view, launcher on her back"]


def save(im, name, view):
    to_34(im.convert("RGB")).save(os.path.join(OUT, name + ".png"))
    with io.open(os.path.join(OUT, name + ".txt"), "w", encoding="utf-8") as fh:
        fh.write(f"{TRIG}, {view}")


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    n = 0
    for key, panels in PANELS.items():
        f = [x for x in glob.glob(os.path.join(SRC, "*.png")) if key in x][0]
        im = Image.open(f).convert("RGB")
        w, h = im.size
        for j, ((l, t, r, b), view) in enumerate(panels):
            save(im.crop((int(l * w), int(t * h), int(r * w), int(b * h))), f"n{key}_{j}", view)
            n += 1
    save(Image.open(os.path.join(SRC, "extra_gray_fullbody.webp")), "gray_front", "full body, front, launcher on her back")
    n += 1
    z = zipfile.ZipFile(r"C:\Users\Owner\Downloads\Tazz with weapon.zip")
    names = [x for x in z.namelist() if x.lower().endswith((".png", ".jpg", ".webp"))]
    for i, name in enumerate(names):
        save(Image.open(io.BytesIO(z.read(name))), f"old{i}", OLD_ZIP[i])
        n += 1
    print(f"{n} frames -> {OUT}")


if __name__ == "__main__":
    main()
