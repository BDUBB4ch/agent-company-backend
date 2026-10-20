"""Rebuild Vor'Shara's LoRA dataset from the 16MP MASTERS, not the damaged squares.

The problem this fixes
----------------------
Her 27 "original" training frames (000-026) were made by squashing 3456x4608
masters into 1024x1024 AND pillarboxing them with black bars. Two separate
kinds of damage:
  1. the bars are training signal -- the model learns a dark vignette
  2. a full-body figure crushed to 1024 leaves her head ~120px, so her FOUR
     EYES collapse to two. That is not a trainer failure, it is preprocessing.

The masters have her head at ~700-900px. A 1024 face crop taken at 1:1 from a
master is a TRUE native crop with no upscaling -- which is the single biggest
lever available for the four eyes.

What it emits per master
------------------------
  body_<stamp>.png  whole figure, bars removed, padded to square with the
                    frame's OWN background tone (never black)
  face_<stamp>.png  1024x1024 cut at native resolution around her head

NOTHING IS DELETED and nothing existing is overwritten -- output goes to a new
folder. Barry's rule: "nothing is redundant, its always useful."

Usage:
    python scripts/rebuild_vorshara_dataset.py --preview
    python scripts/rebuild_vorshara_dataset.py --write
"""
import argparse
import pathlib

from PIL import Image, ImageStat

ROOT = pathlib.Path(__file__).resolve().parent.parent
DESKTOP = pathlib.Path.home() / "Desktop"
# The nested folder is NOT her -- it is her sanctum (the garden atrium from
# canon: reflecting pool, marble columns, vines). Location plates, wrong for a
# character LoRA, but exactly the material a future location LoRA needs, so
# they are routed aside rather than dropped.
CHARACTER_DIR = DESKTOP / "Bia Project/Bia Project/Lady Vor’Shara Vel"
SANCTUM_DIR = CHARACTER_DIR / "Lady Vor'Shara Vel"
OUT = ROOT / "tools" / "ComfyUI" / "input" / "lora_vorshara_v2"
OUT_SANCTUM = ROOT / "tools" / "ComfyUI" / "input" / "_vorshara_sanctum_location"
FACE = 1024

# Captions describe what the frame ACTUALLY shows -- the B Dubb lesson (a wrong
# hat in 24 captions drifted his whole wardrobe). "full body" is NOT claimed
# here because several masters are already close-ups.
CAPTION_BODY = ("@Vorshara, sheer translucent pale lavender floor-length gown, "
                "gold filigree tracery, plain studio background")
CAPTION_BACK = ("@Vorshara, seen from behind, head tentacles with gold cuff bands, "
                "sheer translucent pale lavender gown, plain studio background")
CAPTION_FACE = "@Vorshara, face close-up, four icy pale blue eyes"

# Face detection still misses on these: 004605 locks onto a lantern, 014454 onto
# a gem on her hem, and 010956/021334 crop down onto a single eyeball. Verified
# by eye on the preview sheet. They still contribute their BODY frame -- nothing
# is discarded, only their bad face crop is skipped.
FACE_SKIP = {"20260611_004605", "20260611_014454",
             "20260611_010956", "20260611_021334"}


def bg_tone(im):
    """Background tone sampled from the frame's corners."""
    w, h = im.size
    k = max(8, w // 40)
    patches = [im.crop((0, 0, k, k)), im.crop((w - k, 0, w, k))]
    vals = [ImageStat.Stat(p).median[:3] for p in patches]
    return tuple(int(sum(v[i] for v in vals) / len(vals)) for i in range(3))


def figure_bbox(im, bg):
    """Bounding box of the subject, by difference from the background tone."""
    small = im.resize((im.size[0] // 8, im.size[1] // 8))
    px = small.load()
    W, H = small.size
    xs, ys = [], []
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y][:3]
            if abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2]) > 38:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return (min(xs) * 8, min(ys) * 8, (max(xs) + 1) * 8, (max(ys) + 1) * 8)


def make_body(im, bg, box):
    """Whole figure, square, padded with the real background tone."""
    x0, y0, x1, y1 = box
    pad = int(max(x1 - x0, y1 - y0) * 0.06)
    x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
    x1, y1 = min(im.size[0], x1 + pad), min(im.size[1], y1 + pad)
    crop = im.crop((x0, y0, x1, y1))
    side = max(crop.size)
    out = Image.new("RGB", (side, side), bg)
    out.paste(crop, ((side - crop.size[0]) // 2, (side - crop.size[1]) // 2))
    return out.resize((FACE, FACE), Image.LANCZOS)


def eye_centroid(im):
    """Locate her face by finding her EYES.

    Everything about her is near-monochrome pale grey-lavender except her four
    icy blue eyes, which are the only strongly blue-dominant pixels in frame.
    So blue dominance is a clean face-finder that works on close-ups AND on
    full-body masters -- and correctly finds nothing on the BACK views, which
    is exactly right: a back view has no face to crop.

    Returns (cx, cy) in full-resolution coordinates, or None.
    """
    s = 16
    small = im.resize((im.size[0] // s, im.size[1] // s))
    px = small.load()
    W, H = small.size
    xs, ys = [], []
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y][:3]
            if b > 70 and b - r > 45 and b - g > 25:
                xs.append(x)
                ys.append(y)
    if len(xs) < 4:
        return None

    # Take the DENSEST cluster, not the median. Her four eyes sit in one tight
    # group; the false positives that fooled the median -- a background guard's
    # glowing eyes, a purple lantern, a gem on her hem -- are scattered singles.
    best, bx, by = 0, 0, 0
    for px_, py_ in zip(xs, ys):
        n = sum(1 for qx, qy in zip(xs, ys)
                if abs(qx - px_) <= 6 and abs(qy - py_) <= 6)
        if n > best:
            best, bx, by = n, px_, py_
    # Widen the window for MEASURING the span (the peak above is what locates
    # her; this is only about how far her outermost eyes sit from it). A fixed
    # +/-8 cells could not span a head that fills a landscape master, which is
    # why those cropped down onto a single eyeball.
    rad = max(8, W // 10)
    near = [(x, y) for x, y in zip(xs, ys)
            if abs(x - bx) <= rad and abs(y - by) <= rad // 2]
    cx = sum(x for x, _ in near) / len(near)
    cy = sum(y for _, y in near) / len(near)
    # horizontal spread of the cluster ~ how wide her set of eyes reads, which
    # is what tells us how big her head is in THIS frame
    span = (max(x for x, _ in near) - min(x for x, _ in near) + 1) * s
    return (int(cx * s), int(cy * s), max(span, 1))


def make_face(im, eye):
    """Square crop centred on her eyes, sized to her head, output at 1024.

    Native 1:1 is right for a full-body master (her head is ~800px, so 1024
    frames it). But the landscape masters are ALREADY close-ups where her head
    fills 2000px+, and a fixed 1024 cut there lands on a single eyeball. So the
    crop scales with the measured eye span and is resampled down to 1024 --
    never up, so no frame is ever upscaled.
    """
    cx, cy, span = eye
    side = int(min(max(span * 4.5, FACE), min(im.size)))
    half = side // 2
    left = max(0, min(im.size[0] - side, cx - half))
    top = max(0, min(im.size[1] - side, cy - half - side // 8))
    crop = im.crop((left, top, left + side, top + side))
    return crop if crop.size == (FACE, FACE) else crop.resize((FACE, FACE), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    if not (args.preview or args.write):
        ap.error("give --preview or --write")

    files = sorted(CHARACTER_DIR.glob("*.png"))
    sanctum = sorted(SANCTUM_DIR.glob("*.png"))
    print(f"{len(files)} character masters, {len(sanctum)} sanctum plates")

    if args.write:
        OUT.mkdir(parents=True, exist_ok=True)
        OUT_SANCTUM.mkdir(parents=True, exist_ok=True)
        for p in sanctum:
            im = Image.open(p).convert("RGB")
            im.resize((FACE, int(FACE * im.size[1] / im.size[0])), Image.LANCZOS).save(
                OUT_SANCTUM / f"sanctum_{p.name[3:18]}.png")
        print(f"  routed {len(sanctum)} sanctum plates -> {OUT_SANCTUM.name}")

    tiles = []
    for p in files:
        im = Image.open(p).convert("RGB")
        bg = bg_tone(im)
        stamp = p.name[3:18]
        eye = eye_centroid(im)
        body = make_body(im, bg, (0, 0, im.size[0], im.size[1]))
        if eye is None or stamp in FACE_SKIP:
            why = "back view" if eye is None else "face crop verified bad"
            print(f"  {stamp:<16} {im.size[0]}x{im.size[1]}  BODY ONLY ({why})")
            face = None
        else:
            face = make_face(im, eye)
            print(f"  {stamp:<16} {im.size[0]}x{im.size[1]}  eyes at ({eye[0]},{eye[1]}) span={eye[2]}px")
        if args.write:
            body.save(OUT / f"body_{stamp}.png")
            cap = CAPTION_BACK if eye is None else CAPTION_BODY
            (OUT / f"body_{stamp}.txt").write_text(cap, encoding="utf-8")
            if face is not None:
                face.save(OUT / f"face_{stamp}.png")
                (OUT / f"face_{stamp}.txt").write_text(CAPTION_FACE, encoding="utf-8")
        if args.preview:
            tiles.append((stamp, body, face or Image.new("RGB", (FACE, FACE), (40, 30, 30))))

    if args.preview and tiles:
        tw = 260
        sheet = Image.new("RGB", (tw * 2 * 6, tw * ((len(tiles) + 5) // 6)), (18, 18, 18))
        for i, (stamp, body, face) in enumerate(tiles):
            x, y = (i % 6) * tw * 2, (i // 6) * tw
            sheet.paste(body.resize((tw, tw)), (x, y))
            sheet.paste(face.resize((tw, tw)), (x + tw, y))
        dest = ROOT / "data" / "_vorshara_v2_preview.png"
        sheet.save(dest)
        print(f"\npreview sheet -> {dest}  (left=body, right=face, per master)")
    if args.write:
        print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
