"""Build the Tazz v4 training set.

Barry's rules applied:
  "newest is best"  -> the Aug-6 batch is a PURPOSE-BUILT reference shoot (front, 3/4,
                       profile, full body, close-up), made to spec a few days ago. It
                       carries the identity and gets the heaviest weight.
  coloured suits    -> EXCLUDED (233432 magenta/blue, 233557 maroon/navy). Her spec is a
                       black sleeveless turtleneck one-piece; training coloured armour
                       risks it being learned as identity.
  "i need those eyes" (said of Bia, applied here too) -> native-res iris crops, because at
                       full-frame scale the iris is too small a fraction to survive averaging.

Fixes the v2 failure: v2 rendered a BEARDED MUSCULAR MALE. Every Aug-6 frame is
unambiguously female, so the corrective signal is strong and consistent.

May-7 files are 2-panel composites (face left, body right). The seam is at 0.518, found by
COLUMN DISCONTINUITY. A brightness/uniformity scan gave 0.574 and 0.599 -- those are bright
regions inside the RIGHT panel, not the boundary, and using them left a vertical sliver of
panel 2 down the edge of every face crop. Caught by looking at the preview.

Dry run by default. --preview to look. --write to commit.
"""
import argparse
import pathlib

from PIL import Image

Image.MAX_IMAGE_PIXELS = None

SRC = pathlib.Path(r"C:\Users\Owner\Desktop\Bia Project\Bia Project\Tazz")
DEST = pathlib.Path(__file__).resolve().parents[1] / "tools" / "ComfyUI" / "input" / "lora_tazz_v4"

BASE = ("@Tazz, alien woman, light skin, subtly pointed ears, violet and pink double-ring "
        "irises non-glowing, slightly muscular athletic build, two long dark braids")

COSTUME = "black sleeveless turtleneck one-piece tactical jumpsuit form-fitting, black boots"

# --- NEWEST: the purpose-built Aug-6 reference shoot. Heaviest weight. ---
AUG6 = [
    ("034900", 9, "front close-up portrait, " + COSTUME + ", plain grey studio background"),
    ("034651", 8, "full body standing, " + COSTUME + ", tactical harness with buckles, "
                  "thigh rig, plain grey studio background"),
    ("030730", 7, "front portrait, black sleeveless turtleneck, plain grey studio background"),
    ("032906", 7, "three-quarter portrait, black sleeveless turtleneck, plain grey studio background"),
    ("034254", 7, "left profile portrait, pointed ear clearly visible, black sleeveless turtleneck"),
]

# --- Iris crops from the best iris frame (034900). ---
IRIS_SRC = "034900"
IRIS_CROPS = [
    ("both", 0.26, 0.345, 0.76, 0.445, 5),
    ("wide", 0.16, 0.310, 0.86, 0.490, 4),
]
IRIS_CAPTION = ("@Tazz, extreme close-up of the eyes, violet outer ring with a distinct "
                "magenta-pink inner ring around the pupil, double-ring iris, non-glowing, "
                "dark round pupil, white sclera visible, light skin")

# --- OLDER: May-7 2-panel composites. (fragment, gutter_x, body-panel description) ---
MAY7 = [
    ("231214", 0.518, "jungle clearing beside a crashed escape pod, grey sleeveless "
                      "high-neck top, tactical belt, fingerless gloves, holding a black helmet"),
    ("231549_132c5a4d", 0.518, "full body standing, black sleeveless tank and black cargo "
                      "trousers, black boots, plain grey studio background"),
]
FACE_CAPTION = BASE + ", close-up portrait"

# --- 233826 pair: the ONLY back-view and walking poses Tazz has anywhere. ---
# Boundaries found by FIGURE-EXTENT detection (columns deviating from the backdrop),
# then cut midway through the gaps BETWEEN figures. Guessing at seams sliced a body in
# half; measuring the figures themselves does not.
POSE_SHEETS = [
    ("233826_dbd410c7", [(0.395, 0.700), (0.710, 1.000)],
     "full body, black sleeveless turtleneck and olive cargo trousers, black boots, "
     "plain studio background"),
    ("233826_f759b228", [(0.330, 0.520), (0.548, 0.755), (0.775, 0.965)],
     "full body, black sleeveless turtleneck and olive cargo trousers, black boots, "
     "plain studio background"),
]


def find(frag):
    m = [f for f in SRC.glob("*.png") if frag in f.name]
    return m[0] if m else None


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

    n = 0

    for frag, repeat, extra in AUG6:
        p = find(frag)
        if not p:
            print("MISSING", frag)
            continue
        im = Image.open(p)
        for i in range(repeat):
            if out:
                im.save(out / f"aug6_{frag}_r{i}.png")
                (out / f"aug6_{frag}_r{i}.txt").write_text(BASE + ", " + extra, encoding="utf-8")
            n += 1

    p = find(IRIS_SRC)
    if p:
        im = Image.open(p)
        w, h = im.size
        for name, x0, y0, x1, y1, repeat in IRIS_CROPS:
            crop = im.crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))
            if prev:
                crop.save(prev / f"iris_{name}.png")
            for i in range(repeat):
                if out:
                    crop.save(out / f"iris_{name}_r{i}.png")
                    (out / f"iris_{name}_r{i}.txt").write_text(IRIS_CAPTION, encoding="utf-8")
                n += 1

    for frag, gutter, body_extra in MAY7:
        p = find(frag)
        if not p:
            print("MISSING", frag)
            continue
        im = Image.open(p)
        w, h = im.size
        # Seam found by COLUMN DISCONTINUITY, not by brightness. A composite seam is where
        # two different images butt together, so |diff| between adjacent columns spikes there.
        # The brightness method found a bright region INSIDE the right panel (0.574/0.599)
        # and left a sliver of panel 2 in every face crop. The real seam is 0.518 in all of them.
        cut = int(w * gutter)
        face = im.crop((0, 0, cut - 6, h))
        body = im.crop((cut + 6, 0, w, h))
        # BODY only -- Aug-6 already covers every face angle, so old faces would only
        # dilute the newest material Barry asked to lead with.
        for tag, img, cap in (("body", body, BASE + ", " + body_extra),):
            nm = f"may7_{frag}_{tag}"
            if prev:
                img.copy().resize((img.width // 3, img.height // 3)).save(prev / f"{nm}.png")
            if out:
                img.save(out / f"{nm}.png")
                (out / f"{nm}.txt").write_text(cap, encoding="utf-8")
            n += 1

    for frag, spans, extra in POSE_SHEETS:
        p2 = find(frag)
        if not p2:
            print("MISSING", frag)
            continue
        im = Image.open(p2)
        w, h = im.size
        for j, (x0, x1) in enumerate(spans):
            panel = im.crop((int(w * x0), 0, int(w * x1), h))
            nm = f"pose_{frag}_{j}"
            if prev:
                panel.copy().resize((max(1, panel.width // 3), h // 3)).save(prev / f"{nm}.png")
            if out:
                panel.save(out / f"{nm}.png")
                (out / f"{nm}.txt").write_text(BASE + ", " + extra, encoding="utf-8")
            n += 1

    print("frames %s: %d" % ("WRITTEN" if out else "planned", n))
    print("  233826 pose panels        :", sum(len(s) for _f, s, _e in POSE_SHEETS))
    print("  Aug-6 purpose-built shoot :", sum(r for _f, r, _e in AUG6))
    print("  iris crops (034900)       :", sum(r for *_x, r in IRIS_CROPS))
    print("  May-7 body panels (old)   :", len(MAY7))
    if not out:
        print("DRY RUN - use --preview <dir> then --write")


if __name__ == "__main__":
    main()
