"""Every model file named by the LIVE workflows (workflows/*.json minus the retired LTX-2.3 graphs) and by
comfy_image.py / reel_builder.py must exist in one of ComfyUI's model roots. Prints what's missing; exit 1 if any."""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
ROOTS = ["tools/ComfyUI/models", "D:/LTX25/models", "D:/ComfyUI25/models"]
RETIRED = re.compile(r"comfy_(i2v|t2v)_ltx_api|comfy_t2v_sulphur_api|_ltx_gguf_api")
NAME = re.compile(r'"([^"/\\]+\.(?:safetensors|gguf|pt|pth))"')

have = set()
for r in ROOTS:
    for dirpath, _, files in os.walk(r):
        have.update(files)
live = [f for f in glob.glob("workflows/*.json") if not RETIRED.search(f)]
names = set()
for f in live + ["backend/comfy_image.py", "backend/reel_builder.py"]:
    names |= set(NAME.findall(open(f, encoding="utf-8").read()))
missing = sorted(n for n in names if n not in have and "PLACEHOLDER" not in n)
print(f"{len(live)} live workflows, {len(names)} model names referenced, {len(missing)} missing")
for n in missing:
    print("  MISSING:", n)
sys.exit(1 if missing else 0)
