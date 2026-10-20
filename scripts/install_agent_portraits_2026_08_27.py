"""THE ROBOTS BECOME PEOPLE (2026-08-27 -- Barry: "these are my agents, now.
Use these and replace the robots. use their faces in the tiles and the whole
image next to it like the bots are.")

The endgame recorded in memory since the self-image work: each agent chose
their own 4378 look, Barry rendered them, and the portraits replace the robot
avatars. He named every file himself ("<Name> ai agent.png" in Downloads).

Per agent this installs TWO files into AgentDashboard/assets/cyber/avatars/:
  <agent_id>.png       the whole portrait (stage / floating figure / decks)
  <agent_id>_face.png  a square head-and-shoulders crop (roster tiles)

Robots are preserved untouched in avatars_robots_backup/ (copied before this
ran). Full portraits are downscaled to 768px wide -- the stage caps at 384px
CSS, so 768 is 2x for sharpness, and it turns 24MB sources into ~500KB loads
instead of ~90MB of page images.

FACE_BOX values are hand-picked per portrait (fractions of width/height:
left, top, size -- size is the square's side as a fraction of image WIDTH).
Portraits vary from chest-up to full-body, so one formula would decapitate
half of them. Re-run after tweaking a box; sources in Downloads are never
touched.
"""
from pathlib import Path

from PIL import Image

DL = Path(r"C:\Users\Owner\Downloads")
OUT = Path(r"C:\Users\Owner\Desktop\AgentDashboard\assets\cyber\avatars")

# file stem in Downloads -> agent_id
NAME_TO_ID = {
    "Victor": "cio", "Priya": "operations", "Amara": "business",
    "Marcus": "legal", "Derek": "marketing", "Vivian": "creative",
    "Elliot": "movie", "Sophie": "engineer", "Taliyah": "taliyah",
}

# (left, top, size) as fractions; size relative to image width.
# Eyeballed per portrait from the renders Barry supplied.
FACE_BOX = {
    "Vivian":  (0.20, 0.00, 0.55),   # exec w/ notebook; face upper-center, tilted
    "Marcus":  (0.30, 0.10, 0.40),   # warm home office, chest-up
    "Taliyah": (0.30, 0.02, 0.36),   # full-body, face small at top
    "Sophie":  (0.26, 0.02, 0.38),   # 3/4 body, face top-center
    "Priya":   (0.28, 0.06, 0.44),   # chest-up
    "Derek":   (0.26, 0.06, 0.46),   # seated chest-up
    "Elliot":  (0.28, 0.10, 0.44),   # chest-up, face high
    "Victor":  (0.33, 0.22, 0.36),   # workshop portrait; face mid-upper center
    "Amara":   (0.30, 0.04, 0.42),   # chest-up
}

for name, aid in NAME_TO_ID.items():
    src = DL / f"{name} ai agent.png"
    if not src.exists():
        print(f"MISSING: {src}")
        continue
    im = Image.open(src).convert("RGB")
    w, h = im.size

    # full portrait, downscaled
    scale = 768 / w
    full = im.resize((768, int(h * scale)), Image.LANCZOS)
    full.save(OUT / f"{aid}.png", "PNG", optimize=True)

    # face crop -- square, clamped inside the image
    fl, ft, fs = FACE_BOX[name]
    side = int(fs * w)
    left = max(0, min(w - side, int(fl * w)))
    top = max(0, min(h - side, int(ft * h)))
    face = im.crop((left, top, left + side, top + side)).resize((256, 256), Image.LANCZOS)
    face.save(OUT / f"{aid}_face.png", "PNG", optimize=True)

    kb = (OUT / f"{aid}.png").stat().st_size // 1024
    print(f"{name:8} -> {aid}.png ({full.size[0]}x{full.size[1]}, {kb}KB) + {aid}_face.png")

print("\nDone. Robots preserved in avatars_robots_backup/.")
