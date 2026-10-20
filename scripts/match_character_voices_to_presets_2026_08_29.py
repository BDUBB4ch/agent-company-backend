"""Which Higgsfield PRESET is each character voice?

Barry, 2026-08-29: "the six came from the presets. i chose the best ones.
lets just use those." He picked them on 08-20 and the mapping was never
written down -- so the voice_ids needed to actually generate with them are
unknown.

Claude cannot hear, so this narrows by MEASUREMENT instead: download each
preset preview, track median F0 (pitch) with the same autocorrelation
method as analyze_voice_samples_2026_08_20.py, and rank presets by how
close they sit to each of Barry's character samples. Output is a SHORTLIST
for his ears to confirm -- pitch alone cannot identify a voice, since two
different voices can share a median F0.

Read-only, local, free. No credits, no generation.
"""
import json
import os
import pathlib
import subprocess
import sys
import urllib.request

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
CACHE = ROOT / "data" / "preset_voice_previews"
CACHE.mkdir(parents=True, exist_ok=True)

import imageio_ffmpeg  # noqa: E402
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
SR = 16000

CHARACTERS = {
    "Yannah": r"C:/Users/Owner/Downloads/Yannah Voice.mp3",
    "Tazz":   r"C:/Users/Owner/Downloads/Tazz Voice.mp3",
    "Keth":   r"C:/Users/Owner/Downloads/Keth Voice.mp3",
    "Bia":    r"C:/Users/Owner/Downloads/Bia Voice.mp3",
}


def decode(src, dst):
    subprocess.run([FFMPEG, "-y", "-i", str(src), "-ac", "1", "-ar", str(SR),
                    "-f", "s16le", str(dst)],
                   check=True, capture_output=True)
    return np.frombuffer(dst.read_bytes(), dtype="<i2").astype(np.float32) / 32768.0


def f0_track(x, fmin=70.0, fmax=400.0):
    """Autocorrelation F0, energy + clarity gated -- same shape as the
    08-20 script so numbers are comparable across both."""
    win, hop = int(0.040 * SR), int(0.010 * SR)
    lo, hi = int(SR / fmax), int(SR / fmin)
    out = []
    for i in range(0, max(0, len(x) - win), hop):
        fr = x[i:i + win]
        if float(np.sqrt(np.mean(fr ** 2))) < 0.01:
            continue
        fr = fr - fr.mean()
        ac = np.correlate(fr, fr, "full")[win - 1:]
        if ac[0] <= 0:
            continue
        seg = ac[lo:hi]
        if not len(seg):
            continue
        lag = int(np.argmax(seg)) + lo
        if ac[lag] / ac[0] < 0.35:      # clarity gate: skip unvoiced frames
            continue
        out.append(SR / lag)
    return np.array(out)


def median_f0(path, tmp):
    try:
        x = decode(path, tmp)
    except subprocess.CalledProcessError:
        return None
    f = f0_track(x)
    return float(np.median(f)) if len(f) >= 5 else None


def main():
    voices = json.load(open(ROOT / "data" / "higgsfield_voices.json",
                            encoding="utf-8"))
    tmp = CACHE / "_tmp.raw"

    # --- Barry's character samples ---
    print("HIS CHARACTER SAMPLES")
    targets = {}
    for name, p in CHARACTERS.items():
        if not os.path.isfile(p):
            print(f"  {name:8s} MISSING {p}")
            continue
        m = median_f0(pathlib.Path(p), tmp)
        targets[name] = m
        print(f"  {name:8s} median F0 {m:6.1f} Hz" if m else f"  {name:8s} no pitch")

    # --- presets ---
    print("\nPRESETS (downloading previews once, cached)")
    measured = []
    for v in voices:
        if v.get("voice_type") != "preset":
            continue
        url, vid, nm = v.get("preview_url"), v["voice_id"], v["name"]
        if not url:
            continue
        f = CACHE / f"{nm}.mp3"
        if not f.exists():
            try:
                urllib.request.urlretrieve(url, f)
            except Exception as e:
                print(f"  {nm:9s} download failed: {str(e)[:40]}")
                continue
        m = median_f0(f, tmp)
        if m:
            measured.append((nm, vid, m, v.get("gender")))
    print(f"  measured {len(measured)} presets")

    # --- shortlist ---
    print("\nCLOSEST PRESETS BY PITCH -- confirm by EAR, pitch alone is not proof")
    for name, t in targets.items():
        if not t:
            continue
        ranked = sorted(measured, key=lambda r: abs(r[2] - t))[:4]
        print(f"\n  {name}  (his sample: {t:.1f} Hz)")
        for nm, vid, m, g in ranked:
            print(f"    {nm:9s} {m:6.1f} Hz  {abs(m-t):5.1f} off  "
                  f"{g or '?':6s}  {vid}")

    out = ROOT / "data" / "voice_preset_match_2026_08_29.json"
    json.dump({"targets": targets,
               "presets": [{"name": n, "voice_id": v, "median_f0": m,
                            "gender": g} for n, v, m, g in measured]},
              open(out, "w", encoding="utf-8"), indent=1)
    print(f"\nsaved -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
