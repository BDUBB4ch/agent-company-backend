"""Detached chain for the night of 2026-10-04 (Barry: "i want to get some uploads done first"):
1. wait until restart_when_idle has restarted the backend (after "The Halloween Garden" finishes) + 3 min
2. run scripts/her_shot_test_2026_10_04.py (3 shots through reel_builder._her_still), add a panel entry
3. if all 3 came out at the right sizes: redo her parts of Herb Histories & Science (scripts/redo_her_parts.py),
   then ask Ilnora for one Long (video_queue.make_one) and mark it rush
Log: data/reels/_her_shot_test/chain.log."""
import asyncio
import glob
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data", "reels", "_her_shot_test")
LOG = os.path.join(D, "chain.log")
PY = os.path.join(ROOT, "venv", "Scripts", "python.exe")
PANEL_HTML = os.path.join(os.path.dirname(ROOT), "AgentDashboard", "test-panel.html")
ASSETS = os.path.join(os.path.dirname(ROOT), "AgentDashboard", "assets", "test_panel")
EXPECT = {"short_gown": (768, 1376), "short_carry": (768, 1376), "long_gown": (1376, 768)}


def log(m: str) -> None:
    os.makedirs(D, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {m}\n")


def restarted_since(t0: str) -> bool:
    try:
        lines = open(os.path.join(ROOT, "data", "restart_when_idle.log"), encoding="utf-8").read().splitlines()
    except OSError:
        return False
    return any("restarted" in l and l[:19] > t0 for l in lines)


def panel_entry(ok: bool, notes: list[str]) -> None:
    figs = "".join(
        f'<figure><a href="assets/test_panel/ilnora_shotfix_{n}.png" target="_blank">'
        f'<img src="assets/test_panel/ilnora_shotfix_{n}.png"></a><figcaption>{n}</figcaption></figure>'
        for n in EXPECT if os.path.isfile(os.path.join(ASSETS, f"ilnora_shotfix_{n}.png")))
    block = (f'\n<h2>ILNORA SHOT FIXES — wide frame, faster, outfit carries (2026-10-04 night) · '
             f'<span class="{"ok" if ok else "bad"}">{"SIZES OK" if ok else "CHECK"}</span></h2>\n'
             f'<div class="sub">{" · ".join(notes)}</div>\n<div class="row">{figs}</div>\n')
    html = open(PANEL_HTML, encoding="utf-8").read()
    anchor = 'Click any picture to open it full size.</div>\n'
    if anchor in html:
        tmp = PANEL_HTML + ".tmp"
        open(tmp, "w", encoding="utf-8").write(html.replace(anchor, anchor + block, 1))
        os.replace(tmp, PANEL_HTML)


def main() -> None:
    t0 = time.strftime("%Y-%m-%d %H:%M:%S")
    log("waiting for the restart after The Halloween Garden")
    while not restarted_since("2026-10-04 19:17:52"):
        time.sleep(60)
    time.sleep(180)
    log("restart seen -- running the shot test")
    subprocess.run([PY, os.path.join(ROOT, "scripts", "her_shot_test_2026_10_04.py")], cwd=ROOT)
    test_log = open(os.path.join(D, "test.log"), encoding="utf-8").read() if os.path.isfile(os.path.join(D, "test.log")) else ""
    notes, ok = [], True
    from PIL import Image
    for n, size in EXPECT.items():
        p = os.path.join(ASSETS, f"ilnora_shotfix_{n}.png")
        if not os.path.isfile(p):
            ok = False
            notes.append(f"{n}: MISSING")
            continue
        with Image.open(p) as im:
            good = im.size == (size[0] // 16 * 16, size[1] // 16 * 16)
        ok &= good
        secs = next((l.split(" in ")[1].split("s ")[0] for l in test_log.splitlines() if l[9:].startswith(n + ":")), "?")
        notes.append(f"{n}: {'size ok' if good else 'WRONG SIZE'}, {secs}s")
    panel_entry(ok, notes)
    log("test: " + " | ".join(notes))
    if not ok:
        log("not starting the Long -- test failed")
        return
    log("redoing her parts of Herb Histories & Science (Barry: 'redo just the parts with her')")
    subprocess.run([PY, os.path.join(ROOT, "scripts", "redo_her_parts.py"), "data/reels/20261004_000040"], cwd=ROOT)
    log("redo finished -- see data/reels/20261004_000040/redo.log")
    log("asking Ilnora for the Long")
    code = ("import asyncio, sys, json, glob, os; sys.path.insert(0, 'backend'); os.chdir('backend'); import video_queue as Q\n"
            "async def m():\n"
            "    ok = await Q.make_one('long', 'Barry wants uploads: one Long tonight')\n"
            "    Q._log('rush Long: ' + ('queued' if ok else 'missed'))\n"
            "    for f in sorted(glob.glob(os.path.join(Q.QDIR, 'job_*.json')))[::-1]:\n"
            "        j = json.load(open(f, encoding='utf-8'))\n"
            "        if j['status'] == 'queued' and j['pkg'].get('format') == 'long':\n"
            "            j['rush'] = True; json.dump(j, open(f, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)\n"
            "            Q._log('rush set on ' + j['pkg'].get('title', '')); break\n"
            "asyncio.run(m())\n")
    subprocess.run([PY, "-c", code], cwd=ROOT)
    log("done")


if __name__ == "__main__":
    main()
