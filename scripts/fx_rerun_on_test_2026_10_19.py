"""Re-run the effects (CPU only) over the raw 5 s test clip after Barry's note: "no purple should be there except the sigil"."""
import os, shutil, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.environ.pop("__COMPAT_LAYER", None)
import fx, reel_builder  # noqa: E402
D = os.path.join(ROOT, "data", "fx_test_clip_2026_10_19")
OUT = os.path.join(os.path.expanduser("~"), "Desktop", "Ilnora's Videos", "_TEST effects clip 2026-10-19")
v2 = os.path.join(D, "with_effects_v3.mp4")
shutil.copy2(os.path.join(D, "raw.mp4"), v2)
fx.apply(v2, ["ritual", "sparks", "lightning", "sigil:helm"], 5.0, reel_builder.FORMATS["short"], D, 1, print)
shutil.copy2(v2, os.path.join(OUT, "test clip - with effects v3 (light on things).mp4"))
print("done")
