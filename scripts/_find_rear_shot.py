"""Screen a folder for a specific pose using the vision model, then the HUMAN
(or a native-resolution open) confirms. Per the method rule: the vision model is
a HINT for narrowing, never evidence -- the shortlist gets opened for real."""
import sys, pathlib
sys.path.insert(0, "backend")
import media_understanding as MU

folder = pathlib.Path(sys.argv[1])
files = sorted(folder.glob("*.png"))
for f in files:
    try:
        d = MU.describe_image(f.read_bytes(), question="Is this person seen from the front, the side, or from BEHIND? State the camera angle first, then briefly what they are wearing.") or ""
    except Exception as e:
        print(f"{f.name}: ERROR {e}", flush=True); continue
    d1 = " ".join(d.split())[:150]
    hit = any(w in d.lower() for w in ("from behind", "back view", "her back", "rear view", "back is", "backside", "buttocks", "over her shoulder", "looking back"))
    print(f"{'>>>' if hit else '   '} {f.name}: {d1}", flush=True)
