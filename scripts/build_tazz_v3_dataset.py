"""Build lora_tazz_v3: Barry's 20 new Higgsfield frames + her 29 fixed originals.

Every one of the 20 was opened at full resolution on 2026-08-05 and captioned
from what is actually in the frame -- never from the filename. Captions name
her as a woman (the omission that made v2 render a man), and describe wardrobe
and background so those stay promptable and only her FACE binds to @Tazz.

Deliberately NO mirrored copies. The mirror pass existed because her old set
was ~7 distinct shots repeated; these 20 include real left AND right profiles,
so flipped geometry is no longer needed -- and mirroring would reverse the
asymmetric chest harness for no gain.
"""
import shutil
from pathlib import Path

INPUT = Path(__file__).resolve().parent.parent / "tools" / "ComfyUI" / "input"
NEW = INPUT / "_staging" / "new_tazz"
OLD = INPUT / "lora_tazz"
DEST = INPUT / "lora_tazz_v3"

P = "@Tazz, a woman, "
CAPTIONS = {
    "n01": P + "close-up portrait facing forward, twin dark braids, violet double-ring irises, pointed ears, black sleeveless turtleneck, plain grey studio background",
    "n02": P + "close-up portrait, three-quarter view, twin dark braids, violet double-ring irises, black sleeveless turtleneck, plain grey studio background",
    "n03": P + "profile portrait facing left, twin dark braids, violet iris, pointed ear, black sleeveless turtleneck, plain grey studio background",
    "n04": P + "full body standing facing forward, twin dark braids, violet eyes, black sleeveless top with tactical harness, black cargo pants, black boots, plain grey studio background",
    "n05": P + "close-up portrait facing forward, neutral expression, twin dark braids, violet double-ring irises, black sleeveless turtleneck, plain grey background",
    "n06": P + "close-up portrait, three-quarter view looking away, twin dark braids, violet irises, black sleeveless turtleneck, dark studio background",
    "n07": P + "full body standing in left profile, single long dark braid, black sleeveless top with harness, black trousers, black boots, plain grey studio background",
    "n08": P + "dramatic close-up portrait from below, chin raised, twin dark braids, violet-pink irises, black sleeveless turtleneck, dark background",
    "n09": P + "full body standing in right profile, twin dark braids, black sleeveless top with harness and thigh holster, black trousers, boots, plain grey studio background",
    "n10": P + "full body standing in right profile, twin dark braids, black tactical harness with thigh holster, black trousers, boots, plain grey studio background",
    "n11": P + "close-up portrait facing forward, twin dark braids over shoulders, violet irises, black sleeveless turtleneck, dark grey background",
    "n12": P + "close-up portrait facing forward, hard set expression, twin dark braids, violet-pink irises, black sleeveless top with chest strap, dark background",
    "n13": P + "close-up portrait facing forward, brow furrowed, angry expression, twin dark braids, violet irises, black sleeveless turtleneck, dark textured background",
    "n14": P + "full body standing facing forward, arms at sides, twin dark braids, black sleeveless top with tactical harness, black trousers, boots, plain grey studio background",
    "n15": P + "full body walking, three-quarter view, twin dark braids, black sleeveless top with harness and thigh rig, black trousers, boots, plain grey studio background",
    "n16": P + "running at speed in profile, braids flying, outdoor forest path, dappled daylight, black sleeveless top, black trousers, boots",
    "n17": P + "full body from behind, head turned to look over her shoulder, twin dark braids down her back, black sleeveless top, black trousers, boots, concrete wall background",
    "n18": P + "running at speed in profile, mid-stride, desert scrub and distant mountains, bright daylight, black sleeveless top with harness, black trousers, boots",
    "n19": P + "crouching on one knee, forearms resting on knee, twin dark braids, black sleeveless top with tactical harness, black trousers, boots, dim warehouse with equipment cases",
    "n20": P + "full body from behind looking over her shoulder, single long dark braid, black sleeveless top, black leggings with thigh rig, boots, plain grey studio background",
}


def main():
    DEST.mkdir(exist_ok=True)
    n_new = 0
    for stem, caption in CAPTIONS.items():
        src = NEW / f"{stem}.png"
        if not src.exists():
            raise SystemExit(f"missing {src}")
        shutil.copy2(src, DEST / f"{stem}.png")
        (DEST / f"{stem}.txt").write_text(caption, encoding="utf-8")
        n_new += 1

    n_old = 0
    for png in sorted(OLD.glob("*.png")):
        txt = png.with_suffix(".txt")
        caption = txt.read_text(encoding="utf-8").strip() if txt.exists() else ""
        if "woman" not in caption.lower():
            raise SystemExit(f"{txt.name} missing the gender fix -- run "
                             "prepare_tazz_v3_captions.py first")
        shutil.copy2(png, DEST / f"old_{png.name}")
        (DEST / f"old_{png.stem}.txt").write_text(caption, encoding="utf-8")
        n_old += 1

    total = len(list(DEST.glob("*.png")))
    print(f"lora_tazz_v3: {n_new} new + {n_old} original = {total} frames")


if __name__ == "__main__":
    main()
