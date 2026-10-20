"""Render every effect over real clips from a finished reel into data/fx_test_2026_10_19/ (CPU only) and make
one frame sheet per test. Usage: venv/Scripts/python.exe scripts/test_fx_2026_10_19.py <reel_dir> <her_clip> <plant_clip>"""
import os, shutil, subprocess, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import fx, reel_builder  # noqa: E402

reel, her, plant = sys.argv[1], sys.argv[2], sys.argv[3]
out = os.path.join(ROOT, "data", "fx_test_2026_10_19")
os.makedirs(out, exist_ok=True)
fmt = reel_builder.FORMATS["short"]
tests = [("her", her, ["ritual", "smoke", "sigil:helm"]),
         ("her", her, ["blood", "lightning", "flicker"]),
         ("plant", plant, ["ritual", "embers", "sparks"]),
         ("plant", plant, ["cold", "sigil:vegvisir", "glow"]),
         ("plant", plant, ["ritual", "sigil:pentagram", "smoke", "lightning"])]
for k, (who, src, names) in enumerate(tests):
    clip = os.path.join(out, f"t{k}_{who}.mp4")
    shutil.copy2(os.path.join(reel, src), clip)
    t0 = time.time()
    ok = fx.apply(clip, names, 4.0, fmt, out, k, log=print)
    print(f"test {k} {who} {names}: {'OK' if ok else 'FAILED'} in {time.time() - t0:.0f}s")
    subprocess.run([reel_builder._ffmpeg(), "-v", "error", "-y", "-i", clip, "-vf",
                    "fps=2,scale=270:-1,tile=8x1", "-frames:v", "1", os.path.join(out, f"t{k}_sheet.png")])
