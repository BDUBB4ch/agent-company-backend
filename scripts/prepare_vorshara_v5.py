"""Build the Vor'Shara v5 curriculum folders (2026-08-04 overnight).

Copies frames + captions from lora_vorshara_v4 into two stage folders per the
classification in data/vorshara_v5_sort.txt — every one of the 90 frames was
OPENED and judged by actual framing (5 "body_"-named files are close-ups).
COPY only; lora_vorshara_v4 is never touched. Idempotent.
"""
import shutil
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "tools" / "ComfyUI" / "input"
V4 = SRC / "lora_vorshara_v4"
CU_DIR = SRC / "lora_vorshara_v5_closeups"
BODY_DIR = SRC / "lora_vorshara_v5_body"

# Close-ups (52): head/shoulders or tighter, face dominant.
CU = (
    ["body_20260611_005241", "body_20260611_010956", "body_20260611_011044",
     "body_20260611_021029", "body_20260611_021334"]
    + ["face_20260611_" + t for t in
       "004345 005241 011044 012747 012756 013058 013122 013210 013553 013831 "
       "013857 013925 014112 014735 014929 015048 015247 020526 020528 021029 "
       "021357".split()]
    + ["clip2_w16", "clip2_w17"]
    + ["src_cu_005241", "src_cu_010956", "src_cu_011044", "src_cu_021029",
       "src_cu_021334"]
    + ["src_face_013553", "src_face_013831", "src_face_013925", "src_face_014112",
       "src_face_014735", "src_face_014929", "src_face_015048"]
    + ["vid_v00_0.2s", "vid_v01_0.5s", "vid_v02_0.8s", "vid_v03_1.2s",
       "vid_v04_1.5s", "vid_v05_1.9s", "vid_v06_2.2s", "vid_v07_2.5s",
       "vid_v08_2.9s", "vid_v09_3.2s", "vid_v10_3.5s", "vid_v11_3.9s"]
)


def main():
    all_pngs = {p.stem for p in V4.glob("*.png")}
    cu = set(CU)
    missing = cu - all_pngs
    if missing:
        raise SystemExit(f"CU list names files not on disk: {sorted(missing)}")
    body = all_pngs - cu

    for dest, stems in ((CU_DIR, cu), (BODY_DIR, body)):
        dest.mkdir(exist_ok=True)
        for stem in sorted(stems):
            for ext in (".png", ".txt"):
                src = V4 / (stem + ext)
                if src.exists():
                    shutil.copy2(src, dest / src.name)
    n_cu = len(list(CU_DIR.glob("*.png")))
    n_body = len(list(BODY_DIR.glob("*.png")))
    print(f"closeups: {n_cu} frames, body: {n_body} frames")
    assert n_cu == 52 and n_body == 38, "expected 52/38 split"
    print("OK")


if __name__ == "__main__":
    main()
