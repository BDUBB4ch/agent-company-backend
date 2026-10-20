"""Acoustic analysis of Barry's five character voice samples (2026-08-20).

WHY: Claude cannot HEAR these -- Whisper returns words only and no audio-understanding
model is installed. But pitch, tempo and dynamics are MEASURABLE, and those are three
of the five voice-lock slots. This turns "I can't tell you" into real numbers Barry can
check against his own ears.

WHAT IT MEASURES, honestly:
  * F0 (fundamental frequency) via autocorrelation on voiced frames -> median, range,
    and variability. Median F0 is the objective version of "higher/lower pitched";
    the spread is the objective version of "animated vs flat/monotone".
  * Speaking rate from Whisper word/segment timings -> words per second.
  * Level statistics -> RMS dBFS, peak, crest factor, and how much of the clip is
    silence.

WHAT IT CANNOT MEASURE: timbre, warmth, rasp, accent, breathiness, character. Those
stay Barry's call. No number here should be turned into an adjective about how someone
SOUNDS beyond pitch height and pace.

Decodes with the ffmpeg bundled in imageio-ffmpeg -- no PATH install, no GPU.
"""
import pathlib
import subprocess
import sys
import wave

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import imageio_ffmpeg

DL = pathlib.Path.home() / "Downloads"
FILES = [
    ("B DUBB", "B dub Voice sample.mp3"),
    ("KETH", "Keth Voice.mp3"),
    ("BIA", "Bia Voice.mp3"),
    ("TAZZ", "Tazz Voice.mp3"),
    ("YANNAH", "Yannah Voice.mp3"),
]
SR = 16000
TMP = pathlib.Path(__file__).resolve().parent.parent / "data" / "_voice_tmp"


def decode(src: pathlib.Path, dst: pathlib.Path) -> np.ndarray:
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [exe, "-y", "-i", str(src), "-ac", "1", "-ar", str(SR), "-f", "wav", str(dst)],
        check=True, capture_output=True,
    )
    with wave.open(str(dst), "rb") as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0


def f0_track(x: np.ndarray, fmin: float = 70.0, fmax: float = 400.0) -> np.ndarray:
    """Autocorrelation F0 per 40ms frame. Voiced frames only (energy + clarity gated)."""
    win = int(0.040 * SR)
    hop = int(0.010 * SR)
    lo, hi = int(SR / fmax), int(SR / fmin)
    out = []
    thresh = np.sqrt(np.mean(x ** 2)) * 0.35  # relative energy gate
    for s in range(0, len(x) - win, hop):
        fr = x[s:s + win]
        if np.sqrt(np.mean(fr ** 2)) < thresh:
            continue
        fr = fr - fr.mean()
        ac = np.correlate(fr, fr, mode="full")[win - 1:]
        if ac[0] <= 0:
            continue
        seg = ac[lo:hi]
        if len(seg) == 0:
            continue
        k = int(np.argmax(seg)) + lo
        clarity = ac[k] / ac[0]
        if clarity < 0.35:          # unvoiced / noisy -> discard
            continue
        out.append(SR / k)
    return np.array(out)


def note_for(hz: float) -> str:
    if hz <= 0:
        return "?"
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    n = int(round(12 * np.log2(hz / 440.0))) + 57
    return f"{names[n % 12]}{n // 12}"


def main() -> None:
    TMP.mkdir(exist_ok=True)
    rows = []
    for label, name in FILES:
        src = DL / name
        if not src.exists():
            print(f"{label}: MISSING {src}")
            continue
        x = decode(src, TMP / f"{label}.wav")
        dur = len(x) / SR
        f0 = f0_track(x)
        rms = np.sqrt(np.mean(x ** 2))
        peak = np.max(np.abs(x))
        db = lambda v: 20 * np.log10(v) if v > 0 else -99.0

        # silence share: 20ms frames below -45 dBFS
        fr = int(0.020 * SR)
        frames = x[: len(x) // fr * fr].reshape(-1, fr)
        fr_rms = np.sqrt(np.mean(frames ** 2, axis=1))
        silence = float(np.mean(db(1) if False else (20 * np.log10(np.maximum(fr_rms, 1e-9))) < -45))

        rows.append({
            "label": label, "dur": dur, "n_voiced": len(f0),
            "f0_med": float(np.median(f0)) if len(f0) else 0.0,
            "f0_p10": float(np.percentile(f0, 10)) if len(f0) else 0.0,
            "f0_p90": float(np.percentile(f0, 90)) if len(f0) else 0.0,
            "f0_iqr": float(np.percentile(f0, 75) - np.percentile(f0, 25)) if len(f0) else 0.0,
            "rms_db": db(rms), "peak_db": db(peak), "crest": db(peak) - db(rms),
            "silence": silence * 100,
        })

    print("=" * 96)
    print(f"{'':8} {'dur':>6} {'medF0':>7} {'note':>5} {'p10-p90 Hz':>13} {'spread':>7} "
          f"{'RMS dB':>7} {'peak':>6} {'crest':>6} {'sil%':>5}")
    print("-" * 96)
    for r in rows:
        print(f"{r['label']:8} {r['dur']:6.2f} {r['f0_med']:7.1f} {note_for(r['f0_med']):>5} "
              f"{r['f0_p10']:6.0f}-{r['f0_p90']:<6.0f} {r['f0_iqr']:7.1f} "
              f"{r['rms_db']:7.1f} {r['peak_db']:6.1f} {r['crest']:6.1f} {r['silence']:5.1f}")
    print("=" * 96)

    if len(rows) > 1:
        aliens = [r for r in rows if r["label"] != "B DUBB"]
        if aliens:
            lo = min(aliens, key=lambda r: r["f0_med"])
            hi = max(aliens, key=lambda r: r["f0_med"])
            print(f"\nlowest alien:  {lo['label']} at {lo['f0_med']:.0f} Hz")
            print(f"highest alien: {hi['label']} at {hi['f0_med']:.0f} Hz")
            if lo["f0_med"] > 0:
                st = 12 * np.log2(hi["f0_med"] / lo["f0_med"])
                print(f"spread across the alien cast: {st:.1f} semitones")
        flat = min(rows, key=lambda r: r["f0_iqr"])
        anim = max(rows, key=lambda r: r["f0_iqr"])
        print(f"flattest delivery (least pitch movement): {flat['label']} (IQR {flat['f0_iqr']:.1f} Hz)")
        print(f"most animated (most pitch movement):      {anim['label']} (IQR {anim['f0_iqr']:.1f} Hz)")

    print("\nNOTE: pitch and pace only. Timbre, accent, rasp and character are NOT measured "
          "here and must come from Barry.")


if __name__ == "__main__":
    main()
