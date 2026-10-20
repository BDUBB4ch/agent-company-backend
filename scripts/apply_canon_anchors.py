"""Pin Barry's canon anchors to every caption (2026-08-05/06, his verbatim words).

He supplied a "core anchor" per character to pin across every frame. Structure
of the result is: <anchor>, <what is actually in THIS frame>. The anchor holds
identity and costume constant so those bind to the trigger; the per-frame tail
keeps pose, framing and background promptable.

His anchors, unedited -- do not paraphrase or "improve" them:

  TAZZ   alien woman, light skin, subtly pointed ears, violet and pink
         double-ring irises non-glowing, slightly muscular athletic build,
         two long dark braids, black sleeveless turtleneck one-piece tactical
         jumpsuit form-fitting, black boots
  YANNAH alien woman, athletic lean build, curvy full bust round full butt,
         short asymmetrical wavy hair one side shaved, subtly pointed ears,
         green and brown double-ring fractal irises non-glowing, subtle gold
         freckle-like spots upper cheeks and outer eye area, black form-fitting
         tactical jumpsuit with teal piping one-piece with sleeves, zipped down
         showing cleavage
  KETH   alien being, smooth gray skin, elongated hairless cranium, large eyes
         with vivid green iris no sclera no whites, small low-profile subtly
         pointed ears, slight lean build, approximately four feet tall,
         barefoot, gray facility jumpsuit, dignified not monstrous
  BIA    (see apply_bia_canon_captions.py -- his earlier Eye Lock ruling)

Corrections these forced to captions I had written from the frames:
  - Tazz's costume is a ONE-PIECE jumpsuit, not a top plus cargo pants.
  - Tazz has LIGHT SKIN; her irises are violet AND pink double-ring.
  - Yannah's irises are green and brown DOUBLE-RING FRACTAL, not plain hazel,
    and her gold spots sit on the upper cheeks and outer eye area specifically.

Idempotent -- a caption already carrying the anchor is left alone.
"""
import argparse
import re
from pathlib import Path

INPUT = Path(__file__).resolve().parent.parent / "tools" / "ComfyUI" / "input"

ANCHORS = {
    "tazz": ("@Tazz", "alien woman, light skin, subtly pointed ears, violet and "
             "pink double-ring irises non-glowing, slightly muscular athletic "
             "build, two long dark braids, black sleeveless turtleneck one-piece "
             "tactical jumpsuit form-fitting, black boots"),
    "yannah": ("@Yannah", "alien woman, athletic lean build, curvy full bust round "
               "full butt, short asymmetrical wavy hair one side shaved, subtly "
               "pointed ears, green and brown double-ring fractal irises "
               "non-glowing, subtle gold freckle-like spots upper cheeks and outer "
               "eye area, black form-fitting tactical jumpsuit with teal piping "
               "one-piece with sleeves, zipped down showing cleavage"),
    "keth": ("@Keth", "alien being, smooth gray skin, elongated hairless cranium, "
             "large eyes with vivid green iris no sclera no whites, small "
             "low-profile subtly pointed ears, slight lean build, approximately "
             "four feet tall, barefoot, gray facility jumpsuit, dignified not "
             "monstrous"),
}

# Phrases from my own earlier captions that the anchor now states authoritatively.
# Stripped from the per-frame tail so the caption does not contradict itself.
REDUNDANT = [
    r"a woman,\s*",
    r"twin dark braids(?: over shoulders| down her back)?,\s*",
    r"single long dark braid,\s*",
    r"violet(?:-pink)? (?:double-ring )?iris(?:es)?,\s*",
    r"pointed ears?,\s*",
    r"black sleeveless (?:tactical )?turtleneck,\s*",
    r"black sleeveless top(?: with (?:tactical )?harness(?: and thigh (?:holster|rig))?)?,\s*",
    r"black (?:cargo )?(?:trousers|pants),\s*",
    r"black leggings(?: with thigh rig)?,\s*",
    r"boots,\s*",
    r"gold freckle spots across her cheeks,\s*",
    r"hazel green-brown eyes,\s*",
    r"dark curly hair with shaved undercut sides,\s*",
    r"dark grey tactical bodysuit with teal piping and shoulder pads,\s*",
    r"utility belt,\s*",
    r"black jacket with teal trim,\s*",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("character", choices=sorted(ANCHORS))
    ap.add_argument("folder", help="e.g. lora_tazz_v3")
    args = ap.parse_args()

    trigger, anchor = ANCHORS[args.character]
    marker = anchor.split(",")[1].strip()  # a distinctive middle phrase
    d = INPUT / args.folder
    if not d.is_dir():
        raise SystemExit(f"no such folder: {d}")

    changed = skipped = 0
    for txt in sorted(d.glob("*.txt")):
        caption = txt.read_text(encoding="utf-8").strip()
        if marker in caption:
            skipped += 1
            continue
        tail = caption
        if tail.startswith(trigger):
            tail = tail[len(trigger):].lstrip(", ")
        for pat in REDUNDANT:
            tail = re.sub(pat, "", tail, flags=re.IGNORECASE)
        tail = re.sub(r",\s*,", ", ", tail).strip().strip(",").strip()
        caption = f"{trigger}, {anchor}, {tail}" if tail else f"{trigger}, {anchor}"
        txt.write_text(caption, encoding="utf-8")
        changed += 1
    print(f"{args.folder}: {changed} captions anchored, {skipped} already had it")


if __name__ == "__main__":
    main()
