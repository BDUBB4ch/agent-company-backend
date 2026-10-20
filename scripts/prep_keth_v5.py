"""Build the Keth v5 training set.

TWO THINGS WENT WRONG IN v4 AND BOTH ARE FIXED HERE.

1) WRONG SOURCE IMAGES. v4 was built around hf_20260510_042644 / 042654 /
   042833 (detention floor, red-lit warehouse) at 4x weight. Barry deleted
   those on 2026-08-08 -- THEY WERE NOT KETH. The "small low-profile ears"
   v5 uses ONLY the 17 files Barry confirmed:
   "all the images in his file now are good to use".

2) OVER-DETAILED CAPTIONS. v4 captions carried the full canon spec, so the
   model could explain every image with ordinary words and @Keth learned
   NOTHING -- prompting "@Keth, close-up portrait, gray facility jumpsuit"
   with keth_character_v4 renders an ordinary HUMAN. The LoRAs that worked
   used "@Keth, cinematic still". v5 captions are TRIGGER + FRAMING ONLY.
   No anatomy words at all, which also means no caption can ever teach the
   wrong ear again.

DO NOT write a character description here. Keth's look is defined by BARRY, in
barry-character-canon. This script only selects and crops frames; the model
learns his look from the pixels via the @Keth trigger.

Output note: frames are later de-padded by scripts/depad_training_images.py.
White padding was a mistake -- it starved training (28.5% blank vs 0.3% in the
sets that worked).

Dry run by default. --preview to look. --write to commit.
"""
import argparse
import pathlib

from PIL import Image

Image.MAX_IMAGE_PIXELS = None

SRC = pathlib.Path(r"C:\Users\Owner\Desktop\Bia Project\Bia Project\Keth")
DEST = pathlib.Path(__file__).resolve().parents[1] / "tools" / "ComfyUI" / "input" / "lora_keth_v5"
SIZE = 1024

# --- single frames: (fragment, repeat, framing-only caption) ---
SINGLES = [
    ("045825", 4, "@Keth, close-up portrait"),
    ("045947", 4, "@Keth, close-up portrait"),
    ("050024", 3, "@Keth, close-up portrait"),
    ("050226", 4, "@Keth, three-quarter portrait"),
    ("050534", 4, "@Keth, head and shoulders"),
    ("050747", 4, "@Keth, standing next to a human man in a doorway, full body"),
    ("050944", 4, "@Keth, sitting at ship controls, full body"),
    ("043029_4d6f5c08", 2, "@Keth, three-quarter portrait"),
    ("043029_dc43e77b", 2, "@Keth, three-quarter portrait"),
]

# --- 2x2 grids: every panel a separate frame ---
GRID_2x2 = [
    ("044113_512aff99", "@Keth, full body, plain background"),
    ("044113_6c162a84", "@Keth, full body, plain background"),
    ("044113_97c98eb1", "@Keth, full body, plain background"),
    ("044113_dabd1190", "@Keth, full body, plain background"),
    ("044535", "@Keth, head and shoulders, plain background"),
    ("044720", "@Keth, head and shoulders, plain background"),
]

# --- 2-heads-over-3-bodies sheets. Horizontal cut MEASURED per sheet
#     (gutter sits at 0.506 in one and 0.543 in the other, so one shared
#     constant left a sliver of the head row in the body crops). ---
SHEETS = [
    ("043355", 0.518, "@Keth, head and shoulders, plain background",
                      "@Keth, full body turnaround, plain background"),
    ("043532", 0.552, "@Keth, head and shoulders, plain background",
                      "@Keth, full body turnaround, plain background"),
]


def find(frag):
    m = [f for f in SRC.glob("*.png") if frag in f.name]
    return m[0] if m else None


def square(img):
    side = max(img.size)
    c = Image.new("RGB", (side, side), (255, 255, 255))
    c.paste(img.convert("RGB"), ((side - img.width) // 2, (side - img.height) // 2))
    return c.resize((SIZE, SIZE), Image.LANCZOS)


def emit(img, name, cap, out, prev, counter):
    img = square(img)
    if prev:
        img.save(prev / f"{name}.png")
    if out:
        img.save(out / f"{name}.png")
        (out / f"{name}.txt").write_text(cap, encoding="utf-8")
    counter[0] += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--preview", default=None)
    args = ap.parse_args()

    out = None
    if args.write:
        DEST.mkdir(parents=True, exist_ok=True)
        out = DEST
    prev = pathlib.Path(args.preview) if args.preview else None
    if prev:
        prev.mkdir(parents=True, exist_ok=True)

    n = [0]

    for frag, repeat, cap in SINGLES:
        p = find(frag)
        if not p:
            print("MISSING", frag); continue
        im = Image.open(p)
        for i in range(repeat):
            emit(im, f"one_{frag}_r{i}", cap, out, prev if i == 0 else None, n)

    for frag, cap in GRID_2x2:
        p = find(frag)
        if not p:
            print("MISSING", frag); continue
        im = Image.open(p); w, h = im.size
        for r in range(2):
            for c in range(2):
                panel = im.crop((c * w // 2, r * h // 2, (c + 1) * w // 2, (r + 1) * h // 2))
                emit(panel, f"grid_{frag}_{r}{c}", cap, out, prev, n)

    for frag, cut, head_cap, body_cap in SHEETS:
        p = find(frag)
        if not p:
            print("MISSING", frag); continue
        im = Image.open(p); w, h = im.size
        top = int(h * cut)
        for c in range(2):                                   # head row: 2 panels
            panel = im.crop((c * w // 2, 0, (c + 1) * w // 2, top - 26))
            emit(panel, f"sheet_{frag}_h{c}", head_cap, out, prev, n)
        for c in range(3):                                   # body row: 3 panels
            panel = im.crop((c * w // 3, top + 6, (c + 1) * w // 3, h))
            emit(panel, f"sheet_{frag}_b{c}", body_cap, out, prev, n)

    print("frames %s: %d" % ("WRITTEN" if out else "planned", n[0]))
    print("  source: the 17 files Barry confirmed good on 2026-08-08")
    print("  captions: TRIGGER + FRAMING ONLY (no anatomy words)")
    if not out:
        print("DRY RUN -- use --preview <dir> then --write")


if __name__ == "__main__":
    main()
