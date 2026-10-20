"""Test of the 2026-10-05 backdrop fix (Barry: "stop it now and fix it" / "take care of it"): the redo's shots came back
on the references' blank studio backdrop. Same function her videos call (reel_builder._her_still), with the redo's
REAL shots that failed + the close "sly grin" shot that drifted. -> data/reels/_her_backdrop_test/ + test panel."""
import asyncio
import json
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import comfy_image  # noqa: E402
import llm_router  # noqa: E402
import reel_builder as R  # noqa: E402

D = os.path.join(ROOT, "data", "reels", "_her_scene_first_test")
PANEL_DIR = os.path.join(os.path.dirname(ROOT), "AgentDashboard", "assets", "test_panel")
PANEL_HTML = os.path.join(os.path.dirname(ROOT), "AgentDashboard", "test-panel.html")
LOG = os.path.join(D, "test.log")
SHOTS = json.load(open(os.path.join(ROOT, "data", "reels", "20261004_000040", "redo_shots.json"), encoding="utf-8"))
TESTS = [  # (name, form, shot) -- run in order, the outfit carries like a real video
    ("long_part1", "long", SHOTS[0]),
    ("long_part7_turning", "long", SHOTS[3]),
    ("short_sly_grin", "short", "Leaning in close to the camera with a sly grin, one finger raised"),
]


def log(m: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {m}"
    print(line, flush=True)
    open(LOG, "a", encoding="utf-8").write(line + "\n")


def panel(notes: list[str], names: list[str]) -> None:
    figs = "".join(f'<figure><a href="assets/test_panel/ilnora_scenefirst_{n}.png" target="_blank">'
                   f'<img src="assets/test_panel/ilnora_scenefirst_{n}.png"></a><figcaption>{n}</figcaption></figure>'
                   for n in names)
    block = (f'\n<h2>ILNORA SCENE-FIRST SHOTS — Qwen-Image draws her scene, the editor gives her her face (2026-10-05 early)'
             f'</h2>\n<div class="sub">{" · ".join(notes)}</div>\n<div class="row">{figs}</div>\n')
    html = open(PANEL_HTML, encoding="utf-8").read()
    anchor = 'Click any picture to open it full size.</div>\n'
    if anchor in html:
        tmp = PANEL_HTML + ".tmp"
        open(tmp, "w", encoding="utf-8").write(html.replace(anchor, anchor + block, 1))
        os.replace(tmp, PANEL_HTML)


async def main() -> None:
    os.makedirs(D, exist_ok=True)
    token = comfy_image.REEL_ACTIVE.set(True)
    open(comfy_image._REEL_MARK, "w").write("Ilnora scene-first test")
    notes, names, last = [], [], ""
    try:
        await comfy_image.reel_wait_turn(log)
        await llm_router.unload_all_models()
        for i, (name, form, shot) in enumerate(TESTS):
            t0 = time.time()
            out = await R._her_still("ilnora", {"show": "self", "shot": shot}, form, D, i, log,
                                     last_outfit=last if form == "long" else "Deep plum velvet gown")
            last = R._outfit_of(shot) or last
            if not out:
                log(f"{name}: FAILED")
                notes.append(f"{name}: FAILED")
                continue
            shutil.copy2(out, os.path.join(PANEL_DIR, f"ilnora_scenefirst_{name}.png"))
            names.append(name)
            notes.append(f"{name}: {time.time() - t0:.0f}s")
            log(f"{name}: done in {time.time() - t0:.0f}s")
    finally:
        comfy_image.REEL_ACTIVE.reset(token)
        try:
            os.remove(comfy_image._REEL_MARK)
        except OSError:
            pass
    panel(notes, names)
    log("done")


if __name__ == "__main__":
    asyncio.run(main())
