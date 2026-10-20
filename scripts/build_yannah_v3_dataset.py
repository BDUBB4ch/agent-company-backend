"""Build lora_yannah_v3 from her 24 clean single-subject frames (2026-08-05).

All 37 frames in lora_yannah were opened at full resolution. Two findings:

1. THIRTEEN are multi-panel composites -- main portrait plus thumbnail figures
   (004-008), a four-panel sheet (019), two-figure layouts (022/023, 033/034)
   and two/three-panel sets (025/026, 027). Fed in whole, these teach grid
   layout, which is exactly what made Bia render as a sheet of women.
2. EVERY caption was the same dead boilerplate: "@Yannah, character sheet
   panel, plain studio background" -- no gender, no canon features, and a
   claim of "character sheet panel" that was false for most frames.

The 24 singles are good and varied. They are copied here with captions written
from what is actually in each frame: she is named a woman (the omission that
made Tazz render male), her canon gold freckle SPOTS and hazel green-brown
eyes are named, and wardrobe/background/pose are described so those stay
promptable and only her FACE binds to @Yannah.

lora_yannah is left untouched; the composites are excluded, not deleted, and
can be split into panels later.
"""
import shutil
from pathlib import Path

INPUT = Path(__file__).resolve().parent.parent / "tools" / "ComfyUI" / "input"
SRC = INPUT / "lora_yannah"
DEST = INPUT / "lora_yannah_v3"

COMPOSITES = {"004", "005", "006", "007", "008", "019", "022", "023",
              "025", "026", "027", "033", "034"}

P = "@Yannah, a woman, "
FACE = "gold freckle spots across her cheeks, hazel green-brown eyes, pointed ears, dark curly hair with shaved undercut sides, "
SUIT = "dark grey tactical bodysuit with teal piping and shoulder pads, utility belt, "

CAPTIONS = {
    "009": P + FACE + SUIT + "full body standing in left profile, barefoot, plain grey studio background",
    "010": P + "dark curly hair with shaved undercut sides, " + SUIT + "full body from behind, standing, barefoot, plain grey studio background",
    "011": P + "close-up portrait facing forward, " + FACE + "black jacket with teal trim, plain grey background",
    "012": P + "close-up portrait facing forward, neutral expression, " + FACE + "black jacket with teal trim, plain grey background",
    "013": P + "close-up portrait, three-quarter view looking to the side, " + FACE + "black jacket with teal trim, plain grey background",
    "014": P + "close-up portrait, three-quarter view looking to the side, " + FACE + "black jacket with teal trim, plain grey background",
    "015": P + "close-up portrait facing forward, calm expression, " + FACE + "black jacket with teal trim, plain grey background",
    "016": P + FACE + SUIT + "full body standing facing forward, barefoot, plain grey studio background",
    "017": P + FACE + SUIT + "full body standing facing forward, barefoot, plain grey studio background",
    "018": P + FACE + SUIT + "full body standing facing forward, barefoot, plain grey studio background",
    "020": P + "close-up portrait facing forward, " + FACE + "black jacket with teal trim, plain grey background",
    "021": P + FACE + SUIT + "full body standing facing forward, barefoot, plain grey studio background",
    "024": P + FACE + SUIT + "full body standing facing forward, barefoot, plain grey studio background",
    "028": P + FACE + SUIT + "crouched in a wide combat stance holding a pistol, wearing boots, desert scrub and distant mountains",
    "029": P + FACE + SUIT + "half body, arms folded across her chest, plain grey studio background",
    "030": P + "close-up portrait, three-quarter view looking away, hand raised to her chin, " + FACE + SUIT + "plain grey background",
    "031": P + FACE + SUIT + "half body facing forward, hands behind her back, plain grey studio background",
    "032": P + FACE + SUIT + "leaning forward with one hand resting on her knee, plain grey studio background",
    "035": P + FACE + SUIT + "half body outdoors, arms folded, looking off to the side, desert rocks and yucca, bright daylight",
    "036": P + FACE + SUIT + "crouching on one knee holding a pistol, looking at the camera, plain grey studio background",
    "037": P + FACE + SUIT + "standing turned away, looking back over her shoulder, holding a pistol at her side, plain grey studio background",
    "038": P + FACE + SUIT + "running in profile, mid-stride, barefoot, plain grey studio background",
    "039": P + FACE + SUIT + "kneeling on one knee, hands on her thigh, barefoot, plain grey studio background",
    "040": P + FACE + SUIT + "half body, three-quarter view, arms folded across her chest, plain grey studio background",
}


def main():
    on_disk = {p.stem for p in SRC.glob("*.png")}
    planned = set(CAPTIONS) | COMPOSITES
    if planned != on_disk:
        raise SystemExit(f"mismatch -- unaccounted: {on_disk - planned}, "
                         f"missing from disk: {planned - on_disk}")

    DEST.mkdir(exist_ok=True)
    for stem, caption in CAPTIONS.items():
        shutil.copy2(SRC / f"{stem}.png", DEST / f"{stem}.png")
        (DEST / f"{stem}.txt").write_text(caption, encoding="utf-8")
    print(f"lora_yannah_v3: {len(CAPTIONS)} clean frames "
          f"({len(COMPOSITES)} composites excluded, originals untouched)")


if __name__ == "__main__":
    main()
