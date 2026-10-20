"""Proof for the new Higgsfield references (Barry: "use the new zips", 2026-09-24): one still each for B Dubb and
Tazz through the office's own character path (comfy_image.generate_image -> Qwen 2.1 restage), exactly as
Elliot's still button calls it. B Dubb re-uses Elliot's own #454 prompt so it compares with the old reference."""
import asyncio
import os
import shutil
import sqlite3
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import comfy_image  # noqa: E402
import llm_router  # noqa: E402

OUT = os.path.join(ROOT, "data", "higgs_zips_2026_09_24", "tests")
print("Yannah proof with archive (14) references", flush=True)


async def main():
    os.makedirs(OUT, exist_ok=True)
    c454 = sqlite3.connect(os.path.join(ROOT, "data", "brain.db")).execute(
        "select content from approvals where id=464").fetchone()[0]
    p454 = c454.split("Generated image concept:", 1)[-1].split("\nModel:")[0].strip()
    jobs = [("yannah_464_final", p454)]
    _unused = [("tazz", "@Tazz standing in a dim steel hangar, medium shot from the waist up, looking straight at the "
                     "camera, cold overhead work light, concrete and steel behind her, 35mm photograph")]
    while comfy_image.render_in_progress():
        await asyncio.sleep(20)
    for name, prompt in jobs:
        await llm_router.unload_all_models()
        t = time.time()
        r = await comfy_image.generate_image(prompt)
        if r.get("error"):
            print(name, "FAILED:", r["error"], flush=True)
            continue
        shutil.copy2(r["path"], os.path.join(OUT, f"{name}.png"))
        print(f"{name}: {time.time() - t:.0f}s engine {(r.get('extras') or {}).get('engine')} "
              f"refs {(r.get('extras') or {}).get('references')}", flush=True)


asyncio.run(main())
