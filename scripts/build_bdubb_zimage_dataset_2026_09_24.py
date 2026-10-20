"""B Dubb's Z-Image LoRA dataset (Barry, 2026-09-24: "train on these b dubb").

Sources, every one opened by eye first:
  archive (12).zip  -- 11 renders; sheets split at cut points set by eye on
                       data/zimage_lora/bdubb_splitguide.jpg; #10 EXCLUDED
                       (annotation text baked in, incl. a real gun brand)
  B Dubb with gun.zip -- 4 renders (09-20)
  two videos        -- studio push-in (09-24) + mountain climb (07-19):
                       frames with his face or full figure clear
Every frame becomes 768x1024 (3:4). Narrow panels are padded with the
panel's own edge colour (studio grey), never white, so nothing new is taught.
Captions carry "heavyset" on purpose: the build gets filed under that word
instead of under the trigger, so a prompt saying "medium build" can move it
(Barry wants him slimmer without re-rendering). Trigger: @b-dubb.
Folder holds ONLY frames + captions (the loader reads subfolders).
"""
import glob, io, os, shutil, subprocess, sys, zipfile
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
from config import COMFY_DIR  # noqa: E402

SRC = os.path.join(ROOT, "data", "zimage_lora", "bdubb_src")
OUT = os.path.join(COMFY_DIR, "input", "lora_bdubb_zimage")
DL = r"C:\Users\Owner\Downloads"
TRIG = "@b-dubb"

# key -> list of (box as fractions l,t,r,b ; caption view)
PANELS = {
    "072423": [((0, 0, .33, 1), "full body, three-quarter view"), ((.33, 0, .62, 1), "full body, front"),
               ((.645, 0, 1, 1), "full body, back view")],
    "072426": [((0, 0, .33, 1), "full body, drawing his pistol"), ((.33, 0, .66, 1), "full body, front"),
               ((.66, 0, 1, 1), "full body, three-quarter view")],
    "072048": [((0, 0, 1, 1), "full body, front")],
    "070707": [((0, 0, .329, 1), "face close-up, front"), ((.336, 0, .664, 1), "face close-up, side view"),
               ((.671, 0, 1, 1), "full body, walking")],
    "070307": [((0, 0, .494, .495), "face close-up, three-quarter view"),
               ((0, .505, .494, 1), "face close-up, front"),
               ((.506, 0, 1, 1), "full body, holding his pistol")],
    "070020": [((0, 0, .325, 1), "face close-up, front"), ((.33, 0, .655, 1), "face close-up, side view"),
               ((.66, 0, 1, 1), "full body, front")],
    "070027": [((0, 0, .5, .31), "head and shoulders, front"), ((0, .33, .5, .64), "head and shoulders, three-quarter view"),
               ((.5, 0, 1, 1), "full body, holding his pistol")],
    "070017": [((0, 0, .33, 1), "face close-up, front"), ((.335, 0, .66, 1), "face close-up, side view"),
               ((.665, 0, 1, 1), "full body, holding his pistol")],
    "063334": [((0, 0, 1, 1), "full body, holding his pistol")],
    "064409": [((0, 0, 1, 1), "full body, front")],
}
VIDEOS = [
    (os.path.join(DL, "hf_20260924_052046_019a0b87-b15b-4899-92ed-b6cc0a7f1034.mp4"),
     [(0.3, "full body, front, studio"), (1.2, "upper body, front, studio"), (6.6, "full body, front, studio")]),
    (os.path.join(DL, "hf_20260719_055124_73a799d0-ff98-4d1d-ab53-05f91d5ece69 (1).mp4"),
     [(0.4, "climbing a wet rocky mountainside in the rain"), (4.2, "climbing a wet rocky mountainside in the rain, face visible"),
      (5.3, "climbing a wet rocky mountainside in the rain, face visible"),
      (7.6, "climbing a wet rocky mountainside in the rain, face visible")]),
]


def to_34(im):
    w, h = im.size
    if w / h > 0.75:  # too wide: crop to 3:4 around the centre
        nw = int(h * 0.75)
        l = (w - nw) // 2
        im = im.crop((l, 0, l + nw, h))
    elif w / h < 0.75:  # too narrow: pad with the panel's own edge colour
        nw = int(h * 0.75)
        # pad with the studio background if the panel edge IS background;
        # a face strip's edge is skin or cap, so it gets neutral grey instead
        # (first build padded face strips with the black of the cap -- caught
        # on the check sheet 2026-09-24)
        px = im.getpixel((1, h // 2))
        if sum(px) / 3 < 150:
            px = (150, 150, 150)
        canvas = Image.new("RGB", (nw, h), px)
        canvas.paste(im, ((nw - w) // 2, 0))
        im = canvas
    return im.resize((768, 1024), Image.LANCZOS)


def save(im, name, view):
    to_34(im.convert("RGB")).save(os.path.join(OUT, name + ".png"))
    with io.open(os.path.join(OUT, name + ".txt"), "w", encoding="utf-8") as fh:
        fh.write(f"{TRIG}, heavyset, {view}")


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    n = 0
    for key, panels in PANELS.items():
        f = [x for x in glob.glob(os.path.join(SRC, "*.png")) if key in x][0]
        im = Image.open(f).convert("RGB")
        w, h = im.size
        for j, ((l, t, r, b), view) in enumerate(panels):
            save(im.crop((int(l * w), int(t * h), int(r * w), int(b * h))), f"z{key}_{j}", view)
            n += 1
    z = zipfile.ZipFile(os.path.join(DL, "B Dubb with gun.zip"))
    for i, name in enumerate(x for x in z.namelist() if x.lower().endswith((".png", ".jpg", ".webp"))):
        # views read off the check sheet (the first build captioned all four
        # "full body" -- #0 is a face close-up, #1 a back view)
        view = ["face close-up, front", "full body, back view, weapon holstered",
                "full body, front, weapon holstered", "full body, front, weapon holstered"][i]
        save(Image.open(io.BytesIO(z.read(name))), f"gun{i}", view)
        n += 1
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    for vi, (path, frames) in enumerate(VIDEOS):
        for t, view in frames:
            tmp = os.path.join(ROOT, "data", "zimage_lora", f"_frame_{vi}_{t}.png")
            subprocess.run([ff, "-loglevel", "error", "-y", "-ss", str(t), "-i", path, "-frames:v", "1", tmp], check=True)
            save(Image.open(tmp), f"vid{vi}_{str(t).replace('.', '_')}", view)
            os.remove(tmp)
            n += 1
    print(f"{n} frames -> {OUT}")


if __name__ == "__main__":
    main()
