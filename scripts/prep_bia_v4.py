"""Build the Bia v4 training set.

Barry's rules applied here:
  "newest is best"          -> the Aug-6 Higgsfield batch carries the identity.
                               Older sheets (Feb/March) are dropped, not split.
  iris reference = 023953   -> broad deep-purple ring on an olive/green centre.
                               Weighted hardest so the thin-rim frames cannot out-vote it.
  flecks: temples AND cheeks -> Barry reversed the earlier "temples only" ruling on
                               2026-08-07 after looking again: "im ok with the cheeks".

Excluded and why (see data/bia_dataset_plan_2026-08-07.md):
  Bia with extra eyes.png   FOUR EYES + scaled skin. Four eyes is Vor'Shara's trait.
  Bia overhead shot.png     no face; jungle/pod/helmet scene -- that scene is TAZZ's.
  Bia full front 2.png      blue face markings, no shaved side.
  hf_20260308_*             older design: tousled pixie, NO shaved side, no gold spots.
  hf_20260308_045728 x2     fully violet irises -- the ring has eaten the whole iris.

Dry run by default. --write commits.
"""
import argparse
import pathlib

from PIL import Image

Image.MAX_IMAGE_PIXELS = None

SRC = pathlib.Path(r"C:\Users\Owner\Desktop\Bia Project\Bia Project\Bia")
DEST = pathlib.Path(__file__).resolve().parents[1] / "tools" / "ComfyUI" / "input" / "lora_bia_v4"

BASE = ("@Bia, alien woman, Afro-Latina, athletic build, sleek faded pixie cut shaved on one "
        "side, subtly pointed ears, hazel-gold iris centre with a thick beaded deep-purple "
        "outer ring, non-glowing, subtle gold alien spots across skin, iridescent flecks on "
        "temples and cheekbones")

# (filename-fragment, repeat, extra caption describing THIS frame only)
AUG6 = [
    ("023953", 6, "front portrait, city bokeh background"),          # IRIS REFERENCE
    ("025004", 3, "front close-up portrait"),
    ("024846", 3, "three-quarter view, pointed ear clearly visible"),
    ("024216", 2, "front portrait, overcast daylight"),
    ("024332", 3, "three-quarter left portrait"),
    ("024518", 3, "three-quarter right portrait, dark background"),
    ("024638", 3, "left profile, shaved side of the pixie cut visible"),
    ("025125", 3, "front portrait, neon city lights behind"),
    ("025654", 3, "three-quarter body, black sleeveless zip bodysuit, tactical belt, thigh multitool"),
    ("025931", 1, "action shot mid-leap, cyberpunk rooftop at night, black sleeveless zip suit"),
    ("030031", 1, "action shot mid-leap, warehouse interior, sparks and debris"),
]

# Named stills that are canon-correct. Older, so lower weight than Aug-6.
STILLS = [
    ("Bia Face upclose.png", 2, "close-up portrait, outdoors, natural light"),
    ("Bia Close up 2.png", 2, "close-up portrait, outdoors, natural light"),
    ("Bia full front A.png", 2, "full body, jungle, sleeveless charcoal high-neck top, "
                               "tactical belt, thigh holster, fingerless gloves, black cargo pants, boots"),
    ("Bia right front.png", 2, "half body, jungle, grey sleeveless high-neck top, tactical belt"),
]


IRIS_SRC = "hf_20260806_023953_a214e3d7-aa22-416d-bc89-dcef8476d921.png"
# Native-resolution crops of the REFERENCE iris. At full-frame scale the iris is a tiny
# fraction of the image and gets averaged away; these give the trainer actual iris pixels.
# (name, x0, y0, x1, y1, repeat)
IRIS_CROPS = [
    ("both",  0.24, 0.355, 0.78, 0.455, 4),
    ("wide",  0.15, 0.320, 0.85, 0.500, 3),
    ("left",  0.26, 0.355, 0.50, 0.450, 2),
    ("right", 0.52, 0.355, 0.76, 0.450, 2),
]
IRIS_CAPTION = ("@Bia, extreme close-up of the eyes, hazel-gold iris centre with radiating "
                "fibres, surrounded by a thick beaded deep-purple outer ring of distinct "
                "rounded cells, non-glowing, dark round pupil, white sclera visible, "
                "iridescent flecks on the skin")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    out = None
    if args.write:
        DEST.mkdir(parents=True, exist_ok=True)
        out = DEST

    n = 0
    aug6_files = sorted(SRC.glob("hf_20260806_*.png"))
    for frag, repeat, extra in AUG6:
        match = [f for f in aug6_files if frag in f.name]
        if not match:
            print("MISSING", frag)
            continue
        im = Image.open(match[0])
        for i in range(repeat):
            if out:
                im.save(out / f"aug6_{frag}_r{i}.png")
                (out / f"aug6_{frag}_r{i}.txt").write_text(BASE + ", " + extra, encoding="utf-8")
            n += 1

    for fn, repeat, extra in STILLS:
        src = SRC / fn
        if not src.exists():
            print("MISSING", fn)
            continue
        im = Image.open(src)
        stem = fn.replace(".png", "").replace(" ", "_").lower()
        for i in range(repeat):
            if out:
                im.save(out / f"still_{stem}_r{i}.png")
                (out / f"still_{stem}_r{i}.txt").write_text(BASE + ", " + extra, encoding="utf-8")
            n += 1

    iris_src = SRC / IRIS_SRC
    if iris_src.exists():
        im = Image.open(iris_src); w, h = im.size
        for name, x0, y0, x1, y1, repeat in IRIS_CROPS:
            crop = im.crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))
            for i in range(repeat):
                if out:
                    crop.save(out / f"iris_{name}_r{i}.png")
                    (out / f"iris_{name}_r{i}.txt").write_text(IRIS_CAPTION, encoding="utf-8")
                n += 1
    else:
        print("MISSING iris source", IRIS_SRC)

    print("frames %s: %d" % ("WRITTEN" if out else "planned", n))
    print("  iris crops from the reference frame:", sum(r for *_x, r in IRIS_CROPS))
    print("  Aug-6 (newest, carries identity):", sum(r for _f, r, _e in AUG6))
    print("    of which 023953 (IRIS REFERENCE):", AUG6[0][1])
    print("  older named stills:", sum(r for _f, r, _e in STILLS))
    if out:
        print("dest:", DEST)
    else:
        print("DRY RUN - use --write")


if __name__ == "__main__":
    main()
