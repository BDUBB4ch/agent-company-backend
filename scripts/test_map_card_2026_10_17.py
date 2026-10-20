"""2026-10-17: the map card's tight loop -- no backend, no GPU, no model.
1. video_tool.check(): a part with "map" becomes a card scene (card_plant, no image_prompt).
2. reel_builder._card_scene(): Hyperframes renders the card (or the ffmpeg fallback) into a temp reel dir; the
   clip is exactly the scene's seconds at FPS. Prints the paths so Barry can open them.
Usage: venv/Scripts/python.exe scripts/test_map_card_2026_10_17.py [--long]"""
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import reel_builder  # noqa: E402
import video_tool  # noqa: E402

form = "long" if "--long" in sys.argv else "short"
fmt = reel_builder.FORMATS[form]
fails = []

# 1. her part -> card scene
pkg, why = video_tool.check("ilnora", {
    "title": "map card test", "format": form, "mood": "mystic",
    "parts": [
        {"say": "Datura wrightii grows wild from Mexico up through the southwestern United States.",
         "show": "map", "map": "Mexico, the southwestern United States", "plant": "Datura wrightii", "seconds": 4},
        {"say": "I keep mine behind the greenhouse.", "show": "me"},
    ]})
if not pkg:
    fails.append(f"check() refused: {why}")
else:
    sc = pkg["scenes"][0]
    if sc.get("card") != "map" or sc.get("card_plant") != "Datura wrightii" or "image_prompt" in sc or "plant" in sc:
        fails.append(f"card scene wrong: {json.dumps(sc)}")
    print("scene:", json.dumps(sc))
    if not reel_builder._is_card(sc) or reel_builder._is_self(sc) or reel_builder._plant(sc):
        fails.append("builder routing: card scene seen as self/plant")

# 2. render it
scene = {"narration": "x", "card": "map", "map": "Mexico, the southwestern United States", "card_plant": "Datura wrightii"}
d = tempfile.mkdtemp(prefix="mapcard_")
log_lines = []
t0 = time.time()
png, mp4 = reel_builder._card_scene(scene, 4.35, fmt, d, 0, log_lines.append)
out = os.path.join(d, "c000.mp4")
reel_builder._card_scene_clip(mp4, png, 4.35, 0, out, fmt)
print("\n".join(log_lines))
FFPROBE = os.path.join(ROOT, "tools", "hyperframes", "bin", "ffprobe.exe")
probe = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height,nb_frames,r_frame_rate", "-of", "json", out],
                       capture_output=True, text=True)
try:
    st = json.loads(probe.stdout)["streams"][0]
except Exception:  # noqa: BLE001
    st = {}
    fails.append(f"ffprobe failed: {probe.stderr[:200]}")
want_frames = round(4.35 * reel_builder.FPS)
print(f"clip: {st.get('width')}x{st.get('height')} {st.get('nb_frames')} frames @ {st.get('r_frame_rate')} "
      f"(want {fmt['w']}x{fmt['h']} {want_frames} @ {reel_builder.FPS}) in {time.time() - t0:.0f}s")
if st and (int(st.get("width", 0)) != fmt["w"] or int(st.get("height", 0)) != fmt["h"]
           or abs(int(st.get("nb_frames", 0)) - want_frames) > 1):
    fails.append("clip size/length wrong")
print("still:", png, "| card mp4:", mp4, "| clip:", out)
print("hyperframes path:", "rendered" if mp4 else "FALLBACK text card")

# 3. fact card (step 2): routing + render; a local plant photo if the office has one, never a network fetch here
pkg2, why2 = video_tool.check("ilnora", {
    "title": "fact card test", "format": form, "mood": "mystic",
    "parts": [{"say": "Every part carries scopolamine, between a fifth and six tenths of a percent.",
               "show": "fact", "fact": "Scopolamine 0.2 to 0.6 percent", "plant": "Datura wrightii", "seconds": 3},
              {"say": "I keep mine behind the greenhouse.", "show": "me"}]})
if not pkg2 or pkg2["scenes"][0].get("card") != "fact" or pkg2["scenes"][0].get("fact") != "Scopolamine 0.2 to 0.6 percent":
    fails.append(f"fact check() wrong: {why2 or json.dumps(pkg2['scenes'][0])}")
else:
    print("fact scene:", json.dumps(pkg2["scenes"][0]))
import plant_photos  # noqa: E402
local = plant_photos.photos("Datura wrightii")
reel_builder._plant_ref = lambda species, used, log: ((local[0]["path"], local[0]["credit"]) if local else None)
fscene = {"narration": "x", "card": "fact", "fact": "Scopolamine 0.2 to 0.6 percent", "card_plant": "Datura wrightii"}
t0 = time.time()
fpng, fmp4 = reel_builder._card_scene(fscene, 3.2, fmt, d, 1, log_lines.append)
fout = os.path.join(d, "c001.mp4")
reel_builder._card_scene_clip(fmp4, fpng, 3.2, 1, fout, fmt)
print("\n".join(log_lines[-2:]))
print(f"fact card: {'rendered' if fmp4 else 'FALLBACK'} in {time.time() - t0:.0f}s, photo behind it: "
      f"{'yes (' + os.path.basename(fscene.get('_card_photo', '')) + ')' if fscene.get('_card_photo') else 'none'}, "
      f"credit: {fscene.get('_photo_credit') or '-'} | still: {fpng}")
if not os.path.isfile(fout):
    fails.append("fact clip missing")
print("RESULT:", "PASS" if not fails else "FAIL: " + "; ".join(fails))
sys.exit(1 if fails else 0)
