"""Draw OpenPose skeletons from REAL CHARACTER HEIGHTS.

Why this exists: neither the LoRA nor IP-Adapter controls height — the
character-consistency skill records that IP-Adapter left Keth reading normal
height. ControlNet does control it, but needs a pose image, and the usual route
(comfyui_controlnet_aux / DWPose) degrades to CPU on this AMD machine because
stock Windows onnxruntime wheels have no working ROCm provider. Drawing the
skeleton directly sidesteps that AND gives exact proportions, which a pose
extracted from a photo never would.

TWO CUES, and the first version only had one:
  1. PROPORTION — heads-tall. Head height is roughly constant across adults
     (~9.3in), so a taller character is MORE heads tall. 4ft = ~5.2 heads,
     6'6" = ~8.4 heads. This is the only in-image cue for a SOLO figure.
  2. FRAME OCCUPANCY — how much of the canvas the figure fills. The first
     version always filled the frame, so Keth and Vor'Shara came out the same
     size and only the ratio differed. Now every figure is drawn against a
     shared world scale, so a 4ft character genuinely occupies less canvas.

Honest limit: for a SOLO figure with no scale reference, absolute height is
weakly readable — 6'2" vs 6'6" is ~0.4 heads and will not be obvious. Height
reads properly when two characters share a frame, which is what --with is for.

Usage:
    python scripts/pose_skeleton.py --character keth --out keth_pose.png
    python scripts/pose_skeleton.py --height 6ft6 --out vor_pose.png
    python scripts/pose_skeleton.py --character keth --with vorshara --out pair.png
"""
import argparse
import pathlib
import re

from PIL import Image, ImageDraw

# Canon heights, Barry 2026-08-04. Keth ~4ft is from barry-character-canon.
CHARACTER_HEIGHTS_IN = {
    "bdubb": 74,        # 6'2"
    "tazz": 74,         # 6'2"
    "bia": 69,          # 5'9"
    "yannah": 68,       # 5'8"
    "vorshara": 78,     # 6'6"
    "keth": 48,         # ~4'0"
}

# Adult head height varies far less than body height, which is exactly why
# heads-tall works as a proportion cue at all.
HEAD_IN = 9.3

# Height that fills the canvas top to bottom. This is the SHARED WORLD SCALE --
# every figure in a frame is measured against the same number, which is what
# makes relative height correct. It adapts to the tallest figure present, so a
# giant is never clamped (the first version hardcoded 80in and would have
# silently squashed anything over 6'8").
DEFAULT_WORLD_IN = 80.0
# A plain human at this height can be drawn beside the subject purely as a
# scale yardstick. Without SOMETHING known-sized in frame, a small figure is
# ambiguous between "short" and "far away" -- that is a property of pictures,
# not a bug that better keypoints can fix.
SCALE_REF_IN = 69.0  # 5'9"

LIMBS = [
    (1, 2), (1, 5), (2, 3), (3, 4), (5, 6), (6, 7), (1, 8), (8, 9), (9, 10),
    (1, 11), (11, 12), (12, 13), (1, 0), (0, 14), (14, 16), (0, 15), (15, 17),
]
LIMB_COLORS = [
    (153, 0, 0), (153, 51, 0), (153, 102, 0), (153, 153, 0), (102, 153, 0),
    (51, 153, 0), (0, 153, 0), (0, 153, 51), (0, 153, 102), (0, 153, 153),
    (0, 102, 153), (0, 51, 153), (0, 0, 153), (51, 0, 153), (102, 0, 153),
    (153, 0, 153), (153, 0, 102),
]
POINT_COLORS = [
    (255, 0, 0), (255, 85, 0), (255, 170, 0), (255, 255, 0), (170, 255, 0),
    (85, 255, 0), (0, 255, 0), (0, 255, 85), (0, 255, 170), (0, 255, 255),
    (0, 170, 255), (0, 85, 255), (0, 0, 255), (85, 0, 255), (170, 0, 255),
    (255, 0, 255), (255, 0, 170), (255, 0, 85),
]


def parse_height(s):
    """Accept 6ft2, 6'2, 6'2\", 74in, 74, 188cm."""
    s = str(s).strip().lower().replace('"', "").replace(" ", "")
    m = re.fullmatch(r"(\d+)(?:ft|')(\d+)?", s)
    if m:
        return int(m.group(1)) * 12 + int(m.group(2) or 0)
    m = re.fullmatch(r"([\d.]+)cm", s)
    if m:
        return float(m.group(1)) / 2.54
    m = re.fullmatch(r"([\d.]+)(?:in)?", s)
    if m:
        return float(m.group(1))
    raise ValueError(f"can't parse height: {s}")


def figure_points(height_in, size, cx_frac=0.5, margin=0.05, world_in=DEFAULT_WORLD_IN):
    """Keypoints for one figure, scaled against the shared world height."""
    usable = size * (1 - 2 * margin)
    fig_h = usable * min(height_in / world_in, 1.0)   # frame-occupancy cue
    heads = height_in / HEAD_IN                        # proportion cue
    head_h = fig_h / heads
    top = size * margin + (usable - fig_h)             # feet on a common floor
    cx = size * cx_frac

    y_nose = top + head_h * 0.62
    y_eye = top + head_h * 0.48
    y_ear = top + head_h * 0.52
    y_neck = top + head_h * 1.30
    y_sho = top + head_h * 1.50
    y_hip = top + fig_h * 0.50
    y_knee = top + fig_h * 0.74
    y_ank = top + fig_h * 0.97
    y_elb = (y_sho + y_hip) / 2
    y_wri = y_hip + head_h * 0.15

    sho_w = head_h * 0.80
    hip_w = head_h * 0.52
    arm_out = head_h * 0.30

    return {
        0: (cx, y_nose), 1: (cx, y_neck),
        2: (cx - sho_w, y_sho), 3: (cx - sho_w - arm_out, y_elb),
        4: (cx - sho_w - arm_out * 1.4, y_wri),
        5: (cx + sho_w, y_sho), 6: (cx + sho_w + arm_out, y_elb),
        7: (cx + sho_w + arm_out * 1.4, y_wri),
        8: (cx - hip_w, y_hip), 9: (cx - hip_w, y_knee), 10: (cx - hip_w, y_ank),
        11: (cx + hip_w, y_hip), 12: (cx + hip_w, y_knee), 13: (cx + hip_w, y_ank),
        14: (cx - head_h * 0.22, y_eye), 15: (cx + head_h * 0.22, y_eye),
        16: (cx - head_h * 0.44, y_ear), 17: (cx + head_h * 0.44, y_ear),
    }, heads, head_h


def draw(figures, size):
    im = Image.new("RGB", (size, size), (0, 0, 0))
    d = ImageDraw.Draw(im)
    lw = max(3, int(size / 180))
    r = max(3, int(size / 200))
    for pts in figures:
        for i, (a, b) in enumerate(LIMBS):
            d.line([pts[a], pts[b]], fill=LIMB_COLORS[i % len(LIMB_COLORS)], width=lw)
        for i, xy in pts.items():
            d.ellipse([xy[0] - r, xy[1] - r, xy[0] + r, xy[1] + r],
                      fill=POINT_COLORS[i % len(POINT_COLORS)])
    return im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", help=f"one of {list(CHARACTER_HEIGHTS_IN)}")
    ap.add_argument("--height", help="e.g. 6ft2, 5'9, 74in, 188cm")
    ap.add_argument("--with", dest="second",
                    help="second character sharing the frame — this is where "
                         "height actually READS")
    ap.add_argument("--scale-ref", action="store_true",
                    help="add a plain 5'9\" human beside the subject purely as a "
                         "yardstick. Without a known-sized thing in frame, a small "
                         "figure reads as FAR AWAY rather than SHORT.")
    ap.add_argument("--world", help="height that fills the frame, e.g. 12ft. "
                                    "Defaults to whatever the tallest figure needs, "
                                    "so very large characters are never clamped.")
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--out", required=True, help="written to ComfyUI/input ROOT")
    a = ap.parse_args()

    def resolve(name_or_height):
        key = str(name_or_height).lower()
        if key in CHARACTER_HEIGHTS_IN:
            return CHARACTER_HEIGHTS_IN[key], key
        return parse_height(name_or_height), str(name_or_height)

    if a.character:
        h1, l1 = resolve(a.character)
    elif a.height:
        h1, l1 = parse_height(a.height), a.height
    else:
        ap.error("give --character or --height")

    # Everyone in frame is measured against ONE world height -- that shared
    # scale is what makes relative height correct. It grows for a tall subject
    # so nothing is ever clamped.
    people = [(h1, l1)]
    if a.second:
        people.append(resolve(a.second))
    if a.scale_ref:
        people.append((SCALE_REF_IN, "scale-ref 5'9\""))
    world = (parse_height(a.world) if a.world
             else max(DEFAULT_WORLD_IN, max(h for h, _ in people) * 1.04))

    slots = {1: [0.5], 2: [0.33, 0.67], 3: [0.22, 0.5, 0.78]}[len(people)]
    figs = []
    for (h, lbl), cx in zip(people, slots):
        p, hd, _ = figure_points(h, a.size, cx_frac=cx, world_in=world)
        figs.append(p)
        print(f"  {lbl:<18} {h:5.0f}in  {hd:4.1f} heads  "
              f"{min(h/world,1.0)*100:3.0f}% of frame")
    print(f"  world scale: {world:.0f}in fills the frame")
    if len(people) == 1:
        print("  NOTE: solo figure, no scale reference -- a small figure will read "
              "as FAR AWAY, not short. Use --scale-ref or --with.")

    root = (pathlib.Path(__file__).resolve().parent.parent
            / "tools" / "ComfyUI" / "input")
    draw(figs, a.size).save(root / a.out)
    print(f"-> {root / a.out}")


if __name__ == "__main__":
    main()
