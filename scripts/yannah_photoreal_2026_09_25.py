"""Yannah photo-real test (Barry 2026-09-25: "get yannah images right first").
Her zip pictures (Yanna with Gun.zip, 2026-09-20) match his 08-16 canon look but are rendered like a 3D doll.
ONE change per pass (the edit skill's rule): make it a real photograph; keep everything about her.
Face close-up first, then the front full body. Nothing is installed -- Barry judges first."""
import asyncio
import io
import os
import shutil
import sys
import time
import zipfile

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import comfy_image  # noqa: E402
import llm_router  # noqa: E402

OUT = os.path.join(ROOT, "data", "yannah_photoreal_2026_09_25")
INP = os.path.join(comfy_image.COMFY_DIR, "input")
# Barry: "i think yall didnt say hyper realistic" -- his own canon wording for her rides in every pass
REAL = "Hyper-realistic, documentary realism, not CGI, not anime, not a 3D render. "
KEEP = ("Keep her exact face and features, her emerald-green-and-brown double-ringed eyes, her pointed ears, the "
        "small jewel stud under her right eye, her short twisted locs swept up with warm copper-auburn tips, the "
        "shaved undercut side and gold ear cuff, her warm brown skin tone, her outfit, pose, framing and plain grey "
        "studio background exactly the same.")
FACE = ("Turn this into a real photograph of a real woman: natural skin with visible pores and fine texture, real "
        "individual hair strands in the locs, real catchlights in the eyes, soft studio lighting, shot on an 85mm "
        "portrait lens. " + REAL + KEEP)
BODY = ("Turn this into a real photograph of a real woman standing in a photo studio: natural skin texture, real hair "
        "strands, real matte fabric with seams, stitching and wear on the black tactical jumpsuit and its teal "
        "piping, real leather and metal on the belt and holster, soft studio lighting, full-length fashion "
        "photograph. " + REAL + KEEP)


async def main():
    os.makedirs(OUT, exist_ok=True)
    zf = zipfile.ZipFile(r"C:\Users\Owner\Downloads\Yanna with Gun.zip")
    names = sorted(n for n in zf.namelist() if n.lower().endswith(".png"))
    pick = lambda stamp: next(n for n in names if stamp in n)   # noqa: E731
    jobs = [("face", pick("104218"), FACE),        # the face close-up
            ("body", pick("105040"), BODY)]        # front full body, pistol holstered
    for tag, n, _ in jobs:
        Image.open(io.BytesIO(zf.read(n))).convert("RGB").save(os.path.join(INP, f"yannah_src_{tag}.png"))
        Image.open(io.BytesIO(zf.read(n))).convert("RGB").save(os.path.join(OUT, f"{tag}_original.png"))
    while comfy_image.render_in_progress():
        await asyncio.sleep(20)
    for tag, _, instruction in jobs:
        await llm_router.unload_all_models()
        t = time.time()
        r = await comfy_image.edit_image([f"yannah_src_{tag}.png"], instruction, prefix=f"yannah_real_{tag}")
        if r.get("error"):
            print(tag, "FAILED:", r["error"], flush=True)
            continue
        shutil.copy2(r["path"], os.path.join(OUT, f"{tag}_photoreal.png"))
        print(f"{tag}: {time.time() - t:.0f}s seed {r['seed']}", flush=True)


asyncio.run(main())
