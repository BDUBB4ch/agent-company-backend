"""Barry 2026-10-04 21:40: "yes swap it now, update her avatar too".

Ilnora's new 49-year-old look (Higgsfield, archive (15)/(16).zip):
  face  = set2/hf_20261005_033414 (his pick from my recommendation)
  figure = front view cut from the body sheet hf_20261005_032202 (black tee + leggings)
Writes her face reference + the four "her picture" files (agent_scenes.install_main's set),
backing every old file up first. LOCKED stays (it now protects the new look).
Does NOT touch body.png / body_neutral.png (body sheet wiring waits for his yes).
"""
import datetime
import os
import shutil

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAND = os.path.join(ROOT, "data", "identity", "ilnora", "candidates", "young49_2026_10_04")
FACE_SRC = os.path.join(CAND, "set2", "hf_20261005_033414_0bc7711f-f1e2-4302-86a3-1604670ae3de.png")
BODY_SHEET = os.path.join(CAND, "hf_20261005_032202_4a9505e0-3d2b-4085-a299-d4f4431efbf4.png")
AVATARS = os.path.join(os.path.dirname(ROOT), "AgentDashboard", "assets", "cyber", "avatars")
COMFY_IN = r"D:\ComfyUI25\input"

TARGETS = {
    "face": os.path.join(ROOT, "data", "identity", "ilnora", "face.png"),
    "agent_face": os.path.join(COMFY_IN, "agent_face_ilnora.png"),
    "agent_ref": os.path.join(COMFY_IN, "agent_ref_ilnora.png"),
    "avatar": os.path.join(AVATARS, "ilnora.png"),
    "tile": os.path.join(AVATARS, "ilnora_face.png"),
}


def front_figure(sheet: Image.Image) -> Image.Image:
    """The left (front) figure of the 3-view sheet, padded to 768x1376 with each row's own edge colour."""
    # MEASURED cut (2026-10-04): column profile of pixels darker than 185 -- front figure x 16..~550, the
    # gap between it and the side view bottoms out at x ~556-560 (the first auto-cut at 580 caught the side
    # view's edge; a background-diff detector failed because the backdrop shades left to right).
    im = sheet.convert("RGB")
    w, h = im.size
    px = im.load()
    left, right = 0, 556
    fig = im.crop((left, 0, right, h))
    tw = int(round(h * 768 / 1376))
    out = Image.new("RGB", (tw, h))
    off = (tw - fig.width) // 2
    opx = out.load()
    # Right pad = the clean left-edge backdrop + ONE fixed offset (median right-minus-left over all rows):
    # the cut column carries halo pixels of the side view's arm/hair, so it is never copied row by row.
    import statistics
    delta = [int(statistics.median(px[right - 1, y][c] - px[2, y][c] for y in range(h))) for c in range(3)]
    for y in range(h):
        lc = px[2, y]                                   # clear backdrop at the sheet's left edge
        rc = tuple(max(0, min(255, lc[c] + delta[c])) for c in range(3))
        for x in range(off):
            opx[x, y] = lc
        for x in range(off + fig.width, tw):
            opx[x, y] = rc
    out.paste(fig, (off, 0))
    return out.resize((768, 1376), Image.LANCZOS)


def head_tile(face: Image.Image) -> Image.Image:
    im = face.convert("RGB")
    w, h = im.size                      # 1200x896, face centred ~x610
    side = int(h * 0.70)
    cx = w // 2 + 10
    box = (cx - side // 2, 40, cx + side // 2, 40 + side)
    return im.crop(box).resize((512, 512), Image.LANCZOS)


def main():
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bdir = os.path.join(ROOT, "data", "scene_backups", f"ilnora_before_young49_{stamp}")
    os.makedirs(bdir, exist_ok=True)
    for k, p in TARGETS.items():
        if os.path.isfile(p):
            shutil.copy2(p, os.path.join(bdir, f"{k}__{os.path.basename(p)}"))
    print("backups ->", bdir)

    face = Image.open(FACE_SRC)
    fig = front_figure(Image.open(BODY_SHEET))
    tile = head_tile(face)

    def put(dest, img):
        tmp = dest + ".tmp.png"
        img.save(tmp)
        os.replace(tmp, dest)
        print("wrote", dest, img.size)

    put(TARGETS["face"], face.convert("RGB"))
    put(TARGETS["agent_face"], face.convert("RGB"))
    put(TARGETS["agent_ref"], fig)
    put(TARGETS["avatar"], fig)
    put(TARGETS["tile"], tile)


if __name__ == "__main__":
    main()
