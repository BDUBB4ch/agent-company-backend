"""Build the Keth v4 training set.

Barry's instruction 2026-08-07:
  "train highly on the original keth. on the new images only train on whats good,
   like the eyes"

So:
  ORIGINALS (May-10 batch)  -> the identity. Repeated for high weight.
  NEW (Aug-6 batch)         -> contribute ONLY their good part: the eyes.
                               Cropped tight so the OFF-CANON FLARED EARS are
                               physically outside the frame and cannot be learned.

Rulings this encodes (see data/keth_dataset_plan_2026-08-07.md):
  EARS -> spec wins: small, low-profile. Aug-6 close-ups flare them. Cropped out.
  SKIN -> wrinkled but less extreme; "dignified not monstrous".
  EYES -> images win: vivid green iris, dark pupil, NO sclera, NO whites.

Dry run by default. --preview writes crop previews to LOOK AT (Barry's method rule:
never trust an unviewed crop). --write commits the dataset.
"""
import argparse
import os
import pathlib
import shutil

from PIL import Image

Image.MAX_IMAGE_PIXELS = None

SRC = pathlib.Path(r"C:\Users\Owner\Desktop\Bia Project\Bia Project\Keth")
DEST = pathlib.Path(__file__).resolve().parents[1] / "tools" / "ComfyUI" / "input" / "lora_keth_v4"

BASE = ("@Keth, alien being, smooth gray skin, elongated hairless cranium, large eyes "
        "with vivid green iris no sclera no whites, small low-profile subtly pointed ears, "
        "slight lean build, approximately four feet tall, barefoot, gray facility jumpsuit, "
        "dignified not monstrous")

# ---------------------------------------------------------------- ORIGINALS
# May-10 frames whose ears are ACTUALLY small and low-profile in frame.
# repeat = how many copies go in the set (this is the weighting lever).
ORIGINALS = [
    ("hf_20260510_042644_925a783f-afb2-4091-ac5a-9d2dabbfce8b.png", 4,
     BASE + ", sitting on the floor of a steel detention room, wrists cuffed, full body, side view"),
    ("hf_20260510_042654_9b224968-0a2f-4d69-abf1-b00437bb2626.png", 4,
     BASE + ", sitting on a bench in a detention room, wrist and ankle cuffs, full body, profile"),
    ("hf_20260510_042654_bf591b01-99fb-421d-8b1e-999ff20d12f2.png", 4,
     BASE + ", sitting on the floor against a wall in a bright lab corridor, cuffed, full body"),
    ("hf_20260510_042833_7bd31e74-d977-40ef-a117-0c3f69e10d68.png", 4,
     BASE + ", sitting among wooden crates in a red-lit warehouse, cuffed, full body, profile"),
    ("hf_20260510_042833_a494ad55-5dd2-4905-925d-a2df72fadfd3.png", 4,
     BASE + ", sitting on crates in a red-lit warehouse, cuffed, full body, side view"),
    # New, but its whole frame is on-canon (ears moderate) and it is the ONLY
    # height reference that exists. Flagged for Barry rather than assumed.
    ("hf_20260806_050747_1f81178e-2dd8-4aa2-aa13-59845e4d5298.png", 3,
     BASE + ", standing next to a human man in a doorway for scale, head reaching the man's chest, full body"),
]

# ------------------------------------------------------------- POSE SHEETS
# Clean 2x2 grids, all four panels full-body and on-canon.
POSE_SHEETS_2x2 = [
    "hf_20260510_044113_512aff99-c4e5-415f-8b1c-2a17b2b98ef0.png",
    "hf_20260510_044113_6c162a84-f781-4f60-aed0-19fe2b4819c0.png",
    "hf_20260510_044113_97c98eb1-8a26-4e66-ae01-26d766799b13.png",
    "hf_20260510_044113_dabd1190-8c74-4f7b-a0fb-db8a4eb6ba68.png",
]
POSE_CAPTION = BASE + ", full body, plain white background, standing pose study"

# ------------------------------------------------- TURNAROUNDS: BODIES ONLY
# 2 head panels on the top row (FLARED EARS -> dropped) over 3 body panels
# on the bottom row (correct ears -> kept).
# (filename, top) where top = fraction to cut at. MEASURED, not guessed: the
# horizontal gutter sits at 0.506 in one sheet and 0.543 in the other, so a single
# shared constant left a sliver of the flared-ear head panels in one of them.
TURNAROUNDS = [
    ("hf_20260510_043355_d8b7a27c-9451-43d0-bad6-4df6d897b4e8.png", 0.518),
    ("hf_20260510_043532_538def8b-7a11-41dc-92de-a26610189437.png", 0.552),
]
TURN_CAPTION = BASE + ", full body turnaround, plain white background"

# ------------------------------------------------------- EYE CROPS (NEW ONLY)
# (filename, x0, y0, x1, y1) as fractions. Tuned so the EARS FALL OUTSIDE the box.
# LOOK AT THE PREVIEWS before trusting these.
EYE_CROPS = [
    ("hf_20260806_045825_8ef2a0a8-146b-42e7-bcdd-9cea9d61b66d.png", 0.27, 0.20, 0.73, 0.52),
    ("hf_20260806_045947_bdf218d2-9173-4819-8390-98ba5128d123.png", 0.17, 0.26, 0.83, 0.52),
    ("hf_20260806_050024_0ca92444-fded-4261-8f94-e453dbbe255d.png", 0.12, 0.28, 0.88, 0.55),
    # x0 pulled in from 0.32 -> 0.42: at 0.32 the red ear-interior tissue bled
    # into the left edge, which is the exact colour this crop exists to exclude.
    ("hf_20260806_050226_f7745a14-e4e9-4ef2-9245-38615e2e75b7.png", 0.42, 0.21, 0.92, 0.45),
    ("hf_20260806_050534_a0b2be0d-3673-4c19-b6c0-7dd5e51cf4b7.png", 0.28, 0.22, 0.76, 0.44),
]
# No ear clause, no body clause -- caption ONLY what is inside the crop.
EYE_CAPTION = ("@Keth, extreme close-up of the eyes, large eyes with vivid green iris, "
               "dark round pupil, no sclera, no whites, gray skin with fine lines")


def on_white(img):
    """Pad to a square on WHITE (Barry, 2026-08-07: "put it on white background").

    Padding rather than stretching: the trainer squares every frame anyway, and
    stretching a tall single-figure panel to square distorts the body proportions
    -- which for Keth is the whole point, he is ~4ft and lean. White also stops
    the grey studio backdrop from being learned as part of him.
    """
    side = max(img.size)
    canvas = Image.new("RGB", (side, side), (255, 255, 255))
    canvas.paste(img.convert("RGB"), ((side - img.width) // 2, (side - img.height) // 2))
    return canvas


def save(img, name, caption, out, written):
    if out:
        img.save(out / f"{name}.png")
        (out / f"{name}.txt").write_text(caption, encoding="utf-8")
    written.append(name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--preview", default=None, help="dir to write crop previews into")
    args = ap.parse_args()

    out = None
    if args.write:
        DEST.mkdir(parents=True, exist_ok=True)
        out = DEST
    prev = pathlib.Path(args.preview) if args.preview else None
    if prev:
        prev.mkdir(parents=True, exist_ok=True)

    written = []

    for fn, repeat, cap in ORIGINALS:
        src = SRC / fn
        if not src.exists():
            print("MISSING", fn)
            continue
        im = Image.open(src)
        for i in range(repeat):
            save(im, f"orig_{fn[12:18]}_{fn[19:27]}_r{i}", cap, out, written)

    for fn in POSE_SHEETS_2x2:
        src = SRC / fn
        if not src.exists():
            print("MISSING", fn)
            continue
        im = Image.open(src)
        w, h = im.size
        for r in range(2):
            for c in range(2):
                panel = im.crop((c * w // 2, r * h // 2, (c + 1) * w // 2, (r + 1) * h // 2))
                nm = f"pose_{fn[19:27]}_{r}{c}"
                panel = on_white(panel)
                save(panel, nm, POSE_CAPTION, out, written)
                if prev:
                    panel.copy().resize((panel.width // 3, panel.height // 3)).save(prev / f"{nm}.png")

    for fn, topfrac in TURNAROUNDS:
        src = SRC / fn
        if not src.exists():
            print("MISSING", fn)
            continue
        im = Image.open(src)
        w, h = im.size
        # Bottom row only, cut just below this sheet's own measured gutter.
        top = int(h * topfrac)
        for c in range(3):
            panel = im.crop((c * w // 3, top, (c + 1) * w // 3, h))
            nm = f"turn_{fn[19:27]}_b{c}"
            panel = on_white(panel)
            save(panel, nm, TURN_CAPTION, out, written)
            if prev:
                panel.copy().resize((max(1, panel.width // 3), max(1, panel.height // 3))).save(prev / f"{nm}.png")

    for fn, x0, y0, x1, y1 in EYE_CROPS:
        src = SRC / fn
        if not src.exists():
            print("MISSING", fn)
            continue
        im = Image.open(src)
        w, h = im.size
        box = (int(w * x0), int(h * y0), int(w * x1), int(h * y1))
        crop = im.crop(box)
        nm = f"eyes_{fn[12:18]}"
        # two copies: the eyes are the whole point of including the new images
        for i in range(2):
            save(crop, f"{nm}_r{i}", EYE_CAPTION, out, written)
        if prev:
            crop.save(prev / f"{nm}.png")

    print("frames %s: %d" % ("WRITTEN" if out else "planned", len(written)))
    print("  originals (repeated) :", sum(r for _f, r, _c in ORIGINALS))
    print("  pose panels          :", len(POSE_SHEETS_2x2) * 4)
    print("  turnaround bodies    :", len(TURNAROUNDS) * 3)
    print("  eye crops (x2 each)  :", len(EYE_CROPS) * 2)
    if out:
        print("dest:", DEST)
    else:
        print("DRY RUN - nothing written. Use --preview <dir> then --write")


if __name__ == "__main__":
    main()
