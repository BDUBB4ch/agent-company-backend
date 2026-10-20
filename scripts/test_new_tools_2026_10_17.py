"""2026-10-17: the two new tools, no backend, no model.
1. cad_tool: refuses a script with a forbidden import; builds the smoke box (STEP + STL + PNG) and registers on the DESK.
2. product_video: builds a spot for a real store product (needs the store; skipped with a note when it does not answer).
Usage: venv/Scripts/python.exe scripts/test_new_tools_2026_10_17.py [--no-store]"""
import asyncio
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import cad_tool  # noqa: E402
import product_video  # noqa: E402

fails = []
# 1a. refused script
r = asyncio.run(cad_tool.run("Engineer", {"name": "bad", "script": "import subprocess\nfrom build123d import *\nexport_step(None, 'model.step')"}))
print("refusal:", r.get("error", "")[:90])
if "not allowed" not in r.get("error", ""):
    fails.append("forbidden import was not refused")
# 1b. the box
script = open(os.path.join(ROOT, "tools", "cadgen", "smoke", "box_with_hole.py"), encoding="utf-8").read()
script = script.replace('out = Path(__file__).with_suffix(".step")', 'out = Path("model.step")')
t0 = time.time()
r = asyncio.run(cad_tool.run("Engineer", {"name": "test-box", "script": script, "notes": "tool test"}))
print(f"cad_generate in {time.time() - t0:.0f}s:", json.dumps({k: r.get(k) for k in ("saved", "files", "preview_png", "error", "tell_barry")}, default=str)[:400])
if not r.get("saved") or "stl" not in (r.get("files") or {}):
    fails.append(f"cad_generate failed: {r.get('error')} {str(r.get('output'))[-200:]}")
elif not r.get("preview_png"):
    print("NOTE: no preview PNG (Edge snapshot) -- STEP/STL fine")
# 2. product spot
if "--no-store" not in sys.argv:
    t0 = time.time()
    r = asyncio.run(product_video.run("Creative", {
        "product": "Bionova", "headline": "Feed the whole root zone",
        "bullets": ["Complete base nutrient, start to finish", "Mixes clean, no clogged lines", "One bottle, every stage"],
        "format": "vertical", "seconds": 12}))
    print(f"product_video in {time.time() - t0:.0f}s:", json.dumps({k: r.get(k) for k in ("saved", "video", "product", "error", "tell_barry")}, default=str)[:500])
    if r.get("error") and "store did not answer" in r["error"]:
        print("NOTE: store offline -- spot not tested")
    elif not r.get("saved"):
        fails.append(f"product_video failed: {r.get('error')}")
print("RESULT:", "PASS" if not fails else "FAIL: " + "; ".join(fails))
sys.exit(1 if fails else 0)
