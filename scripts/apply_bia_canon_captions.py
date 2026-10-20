"""Write Barry's Bia canon into her captions (2026-08-05 Eye Lock ruling).

None of her 42 captions mentioned eyes, skin spots or temples -- so her iris,
which is the thing that kept drifting, was never anchored by a single word.
His verbatim spec:

    alien woman, Afro-Latina, athletic build, sleek faded pixie cut shaved on
    one side, subtly pointed ears, hazel-green eyes with gold flecks and
    deep-purple double-ring fractal iris non-glowing, subtle gold alien spots
    across skin, faint iridescent spots on temples only

The identity clause is inserted right after the @Bia trigger so it binds to
her, while whatever the original caption said about pose, wardrobe and
background is preserved and stays promptable.

Idempotent. Operates on a FOLDER argument so it can be pointed at the v4 set
without touching a folder that is mid-training.
"""
import argparse
from pathlib import Path

INPUT = Path(__file__).resolve().parent.parent / "tools" / "ComfyUI" / "input"

CANON = ("a woman, Afro-Latina alien, athletic build, sleek faded pixie cut "
         "shaved on one side, subtly pointed ears, hazel-green eyes with gold "
         "flecks and a deep-purple double-ring fractal iris, non-glowing, "
         "subtle gold alien spots across her skin, faint iridescent spots on "
         "her temples only")
MARKER = "double-ring fractal iris"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", help="e.g. lora_bia_v4")
    args = ap.parse_args()
    d = INPUT / args.folder
    if not d.is_dir():
        raise SystemExit(f"no such folder: {d}")

    changed = skipped = 0
    for txt in sorted(d.glob("*.txt")):
        caption = txt.read_text(encoding="utf-8").strip()
        if MARKER in caption:
            skipped += 1
            continue
        if caption.startswith("@Bia"):
            rest = caption[len("@Bia"):].lstrip(", ")
            caption = f"@Bia, {CANON}, {rest}" if rest else f"@Bia, {CANON}"
        else:
            caption = f"@Bia, {CANON}, {caption}"
        txt.write_text(caption, encoding="utf-8")
        changed += 1
    print(f"{args.folder}: {changed} captions updated, {skipped} already canon")


if __name__ == "__main__":
    main()
