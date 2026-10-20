"""Tighten every agent's IP-Adapter face reference (Barry, 2026-08-28:
"thats not MY Amara's face").

ROOT CAUSE, measured on Elliot: IP-Adapter reads EVERYTHING in the
reference, not just the face. His crop carried his portrait's dark teal
background and a cyan neon streak, and at weight 0.85 those became the
room and the wardrobe in every render -- twice, ignoring his own written
scene. Dropping the weight to 0.55 fixed the scenes and cost identity,
which is what made Amara stop looking like herself.

The weight was never the real lever. A crop that is FACE AND LITTLE ELSE
can run at high weight: identity holds AND the prompt still owns the room.
This centre-crops each existing reference to remove the background margin,
then the build script puts the weight back up.

Originals kept as agent_face_<id>_loose.png -- reversible.
"""
import os
import shutil

from PIL import Image

INPUT = os.path.join(os.path.dirname(__file__), "..", "tools", "ComfyUI", "input")
KEEP = 0.66          # centre fraction retained -- drops the outer margin
OUT_PX = 384         # up from 256: more face detail for the adapter


def main():
    for name in sorted(os.listdir(INPUT)):
        if not (name.startswith("agent_face_") and name.endswith(".png")):
            continue
        if "_loose" in name:
            continue
        path = os.path.join(INPUT, name)
        backup = path.replace(".png", "_loose.png")
        if not os.path.exists(backup):
            shutil.copyfile(path, backup)
        im = Image.open(backup).convert("RGB")
        w, h = im.size
        cw, ch = int(w * KEEP), int(h * KEEP)
        # horizontally centred; biased slightly ABOVE centre because a
        # head-and-shoulders crop puts the face in the upper half.
        left = (w - cw) // 2
        top = max(0, int(h * 0.5 - ch * 0.58))
        im.crop((left, top, left + cw, top + ch)) \
          .resize((OUT_PX, OUT_PX), Image.LANCZOS).save(path)
        print(f"{name}: {w}x{h} -> {OUT_PX}x{OUT_PX} (kept centre {KEEP:.0%})")


main()
