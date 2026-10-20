"""Add Barry's 22 new Higgsfield frames to lora_yannah_v3 (2026-08-06).

Every frame opened at full resolution before captioning. Each caption is his
canon anchor (verbatim) plus what is actually in THAT frame -- pose, framing,
setting -- so identity binds to @Yannah while pose and location stay
promptable.

His anchor:
  alien woman, athletic lean build, curvy full bust round full butt, short
  asymmetrical wavy hair one side shaved, subtly pointed ears, green and brown
  double-ring fractal irises non-glowing, subtle gold freckle-like spots upper
  cheeks and outer eye area, black form-fitting tactical jumpsuit with teal
  piping one-piece with sleeves, zipped down showing cleavage

Coverage these add that her old set lacked: true left AND right profiles, a
low-angle, three distinct expressions, a running shot, and three real
environments (ship corridor, city bridge, stone ruins).
"""
import shutil
from pathlib import Path

INPUT = Path(__file__).resolve().parent.parent / "tools" / "ComfyUI" / "input"
NEW = INPUT / "_staging" / "new_yannah"
DEST = INPUT / "lora_yannah_v3"

A = ("@Yannah, alien woman, athletic lean build, curvy full bust round full butt, "
     "short asymmetrical wavy hair one side shaved, subtly pointed ears, green and "
     "brown double-ring fractal irises non-glowing, subtle gold freckle-like spots "
     "upper cheeks and outer eye area, black form-fitting tactical jumpsuit with "
     "teal piping one-piece with sleeves, zipped down showing cleavage, ")

CAPTIONS = {
    "y01": A + "close-up portrait facing forward, direct gaze, plain grey studio background",
    "y02": A + "close-up portrait facing forward, neutral expression, plain grey studio background",
    "y03": A + "close-up portrait, three-quarter view looking to her left, plain grey studio background",
    "y04": A + "close-up portrait, three-quarter view looking to her right, plain grey studio background",
    "y05": A + "head and shoulders turned away in three-quarter back view, looking to the side, dark grey studio background",
    "y06": A + "close-up portrait facing forward, calm expression, plain grey studio background",
    "y07": A + "close-up portrait facing forward, chin level, plain grey studio background",
    "y08": A + "full profile portrait facing right, shaved side of her head toward camera, plain grey studio background",
    "y09": A + "close-up portrait from below, chin raised, looking up, dark interior background",
    "y10": A + "close-up portrait, chin raised, looking past the camera, plain grey studio background",
    "y11": A + "profile portrait facing left, plain grey studio background",
    "y12": A + "close-up portrait facing forward, faint smile, plain grey studio background",
    "y13": A + "half body facing forward, arms at her sides, plain grey studio background",
    "y14": A + "close-up portrait, one hand raised near her shoulder, looking at the camera, soft indoor background",
    "y15": A + "full body standing facing forward, black boots, plain grey studio background",
    "y16": A + "half body, one arm raised behind her head, looking off to the side, spacecraft interior with control panels, warm light",
    "y17": A + "full body standing facing forward, black boots, stone columns and grey wall behind her",
    "y18": A + "full body standing facing forward, relaxed stance, black boots, plain grey studio background",
    "y19": A + "full body walking, spacecraft corridor with lit panels and screens, cool blue light",
    "y20": A + "running at speed in profile, mid-stride, black boots, city bridge at dusk with motion-blurred traffic",
    "y21": A + "crouching on one knee, forearm resting on her knee, looking at the camera, spacecraft interior",
    "y22": A + "full body from behind, turned to look back over her shoulder, plain grey studio background",
}


def main():
    if not DEST.is_dir():
        raise SystemExit(f"{DEST} missing -- run build_yannah_v3_dataset.py first")
    added = 0
    for stem, caption in CAPTIONS.items():
        src = NEW / f"{stem}.png"
        if not src.exists():
            raise SystemExit(f"missing {src}")
        shutil.copy2(src, DEST / f"{stem}.png")
        (DEST / f"{stem}.txt").write_text(caption, encoding="utf-8")
        added += 1
    total = len(list(DEST.glob("*.png")))
    print(f"added {added} new frames -> lora_yannah_v3 now {total} frames")


if __name__ == "__main__":
    main()
