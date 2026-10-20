"""Build lora_bia_v4: Barry's 11 Eye Lock frames + her cleaned 42 (2026-08-06).

All 11 opened at full resolution. They ARE the Eye Lock spec made visible:
deep-purple double ring around a hazel-green/gold iris, gold spots across the
skin, iridescent shimmer on the temples specifically. Her old 42 frames never
had a single caption mentioning eyes, which is why her renders wandered --
these do, and his anchor is applied to all of them.

Note on n09-n11: the two action frames and the concrete-wall shot show her in
a plain black tank/sleeveless rig rather than the pixie-and-tank of the studio
set, and n10/n11 are stylised cyberpunk action plates. Kept -- Barry's rule is
that nothing is redundant -- but captioned honestly so the outfit and the
stylisation stay promptable instead of binding to her face.
"""
import shutil
from pathlib import Path

INPUT = Path(__file__).resolve().parent.parent / "tools" / "ComfyUI" / "input"
NEW = INPUT / "_staging" / "new_bia"
OLD = INPUT / "lora_bia_v3"
DEST = INPUT / "lora_bia_v4"

A = ("@Bia, a woman, Afro-Latina alien, athletic build, sleek faded pixie cut "
     "shaved on one side, subtly pointed ears, hazel-green eyes with gold flecks "
     "and a deep-purple double-ring fractal iris, non-glowing, subtle gold alien "
     "spots across her skin, faint iridescent spots on her temples only, ")

CAPTIONS = {
    "n01": A + "close-up portrait facing forward, direct gaze, black tank top, overcast city ruins blurred behind her",
    "n02": A + "tight close-up portrait facing forward, neutral expression, black top, blurred grey outdoor background",
    "n03": A + "close-up portrait, three-quarter view looking to her right, black tank top, blurred green and grey outdoors",
    "n04": A + "close-up portrait, three-quarter view looking past the camera, black tank top, dark background",
    "n05": A + "profile portrait facing right, shaved side toward camera, black tank top, dark blurred foliage",
    "n06": A + "profile portrait facing left, shaved side and pointed ear clear, black tank top, overcast outdoor background",
    "n07": A + "extreme close-up portrait facing forward, both eyes filling the frame, blurred outdoor background",
    "n08": A + "close-up portrait facing forward, faint smile, black tank top, neon-lit futuristic city skyline blurred behind her",
    "n09": A + "half body, three-quarter view, one hand on a thigh holster, black sleeveless tactical top with utility belt, weathered concrete wall behind her",
    "n10": A + "full body leaping mid-air in profile, black sleeveless tactical suit with thigh holster and fingerless gloves, rain and sparks, neon-lit industrial city at night, dramatic cinematic action lighting",
    "n11": A + "full body leaping mid-air, black long-sleeved tactical suit with thigh holster and boots, sparks and smoke, dim industrial interior, dramatic cinematic action lighting",
}


def main():
    if not OLD.is_dir():
        raise SystemExit(f"{OLD} missing -- run prepare_bia_v3.py --write first")
    DEST.mkdir(exist_ok=True)

    for stem, caption in CAPTIONS.items():
        src = NEW / f"{stem}.png"
        if not src.exists():
            raise SystemExit(f"missing {src}")
        shutil.copy2(src, DEST / f"{stem}.png")
        (DEST / f"{stem}.txt").write_text(caption, encoding="utf-8")

    carried = 0
    for png in sorted(OLD.glob("*.png")):
        txt = png.with_suffix(".txt")
        caption = txt.read_text(encoding="utf-8").strip() if txt.exists() else ""
        shutil.copy2(png, DEST / f"old_{png.name}")
        (DEST / f"old_{png.stem}.txt").write_text(caption, encoding="utf-8")
        carried += 1

    total = len(list(DEST.glob("*.png")))
    print(f"lora_bia_v4: {len(CAPTIONS)} Eye Lock frames + {carried} carried "
          f"= {total} frames")
    print("now run: apply_bia_canon_captions.py lora_bia_v4")


if __name__ == "__main__":
    main()
