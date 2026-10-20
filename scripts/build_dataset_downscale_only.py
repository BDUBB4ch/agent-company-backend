"""Build a LoRA training folder from ORIGINAL images -- DOWNSCALE ONLY.

Barry, 2026-08-09: "use original images, not the ones you altered" and
"no need for white padding".

What this does and does NOT do:
  * DOES copy the originals to a NEW folder under tools/ComfyUI/input/.
    The source folder is READ ONLY. Nothing is overwritten, ever.
  * DOES downscale so the long edge is at most 1024. SDXL trains at 1024;
    the pre-flight guard rejects anything larger, and oversized frames are
    what froze the PC on 2026-08-07 (182 MPx set, 13.45 s/step, offloaded to
    system RAM).
  * DOES NOT pad to square on white. That is exactly what
    normalize_training_images.py does, and it is post-mortem bug 2: 28-37%
    of every frame became blank white and the LoRA learned essentially
    nothing. Aspect ratio is preserved.
  * DOES NOT crop. Cropping throws away the edges of the frame, which
    matters for full-body shots.
  * Writes a MINIMAL caption per image. Post-mortem bug 3: captions carrying
    the full canon spec let the model explain the image with ordinary words,
    so the @trigger learns nothing. The captions that actually worked were
    "@Keth, cinematic still".

Mixed aspect ratios are fine as long as the training node runs in
bucket_mode -- this script reports the distinct output sizes so the caller
knows whether bucket_mode is required.

Usage:
  python scripts/build_dataset_downscale_only.py <dest_folder> <trigger> <src>...
  python scripts/build_dataset_downscale_only.py lora_yannah_v4 @Yannah "C:/.../Yannah/New Yannah.zip"
"""
import argparse
import collections
import io
import pathlib
import shutil
import sys
import zipfile

from PIL import Image

Image.MAX_IMAGE_PIXELS = None
MAX_EDGE = 1024
ROOT = pathlib.Path(__file__).resolve().parents[1]
INPUT = ROOT / "tools" / "ComfyUI" / "input"
EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def iter_sources(src: pathlib.Path):
    """Yield (name, PIL.Image) from a folder or a zip, non-recursively."""
    if src.is_dir():
        for p in sorted(src.iterdir()):
            if p.suffix.lower() in EXTS:
                yield p.name, Image.open(p)
    elif src.suffix.lower() == ".zip":
        with zipfile.ZipFile(src) as z:
            for n in sorted(z.namelist()):
                if pathlib.Path(n).suffix.lower() in EXTS:
                    yield pathlib.Path(n).name, Image.open(io.BytesIO(z.read(n)))
    else:
        raise SystemExit(f"not a folder or zip: {src}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dest", help="folder name under tools/ComfyUI/input")
    ap.add_argument("trigger", help="caption trigger, e.g. @Yannah")
    ap.add_argument("sources", nargs="+", help="source folders and/or .zip files")
    ap.add_argument("--caption", default="cinematic still",
                    help="tail of the caption after the trigger")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    dest = INPUT / a.dest
    if dest.exists() and not a.dry_run:
        backup = INPUT / f"_{a.dest}_replaced"
        if backup.exists():
            shutil.rmtree(backup)
        shutil.move(str(dest), str(backup))
        print(f"existing {a.dest} moved aside to {backup.name} (not deleted)")
    if not a.dry_run:
        dest.mkdir(parents=True, exist_ok=True)

    sizes = collections.Counter()
    n = 0
    skipped = []
    for src in a.sources:
        for name, im in iter_sources(pathlib.Path(src)):
            w, h = im.size
            if max(w, h) > MAX_EDGE:
                scale = MAX_EDGE / max(w, h)
                new = (max(1, round(w * scale)), max(1, round(h * scale)))
                im = im.convert("RGB").resize(new, Image.LANCZOS)
            else:
                im = im.convert("RGB")
            # SDXL latents need dimensions divisible by 8
            w2, h2 = im.size
            w2, h2 = (w2 // 8) * 8, (h2 // 8) * 8
            if w2 < 256 or h2 < 256:
                skipped.append(f"{name} too small ({im.size})")
                continue
            if (w2, h2) != im.size:
                im = im.crop((0, 0, w2, h2))   # <=7px trim to hit /8, never a real crop
            sizes[im.size] += 1
            n += 1
            out = dest / f"{n:03d}.png"
            if not a.dry_run:
                im.save(out)
                (dest / f"{n:03d}.txt").write_text(
                    f"{a.trigger}, {a.caption}", encoding="utf-8")

    print(f"\n{a.dest}: {n} images{' (DRY RUN)' if a.dry_run else ''}")
    for size, count in sizes.most_common():
        print(f"   {size[0]}x{size[1]}  x{count}")
    for s in skipped:
        print(f"   SKIPPED {s}")
    total_mpx = sum(w * h for (w, h), c in sizes.items() for _ in range(c)) / 1e6
    print(f"   total {total_mpx:.1f} MPx")
    if len(sizes) > 1:
        print("   >>> MIXED SIZES: this dataset REQUIRES bucket_mode=True")
    else:
        print("   >>> uniform size: bucket_mode not required")
    print(f"   caption: \"{a.trigger}, {a.caption}\"")


if __name__ == "__main__":
    sys.exit(main())
