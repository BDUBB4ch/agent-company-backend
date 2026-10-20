"""Qwen-Image BASE runner -- text-to-image on the 20B model, locally.

    ./venv/Scripts/python.exe scripts/qwen_t2i.py "<prompt>" [prefix] [WxH] [negative]

Why this exists (2026-08-28c handoff): SDXL is the bottleneck -- framing
ignored, wardrobe invented, mangled hands, mole speckle from detail terms.
Qwen-Image base is 20B with a Qwen2.5-VL text encoder, Apache 2.0
(commercial-safe for B Dubb, unlike Kontext). This runs the Q4_K_S GGUF
(12.14GB, fits the 16GB card) with the Lightning 8-step V2.0 LoRA.

Native-ish sizes that behave: 1328x1328 (1:1), 1140x1472 (3:4 portrait),
928x1664 (9:16 full-body), 1664x928 (16:9). Default 1024x1024 for speed.

ComfyUI must already be running on 8188 (backend/comfy_image.ensure_running,
or scripts that start it). Negative prompt works even at cfg 1.0? No -- at
cfg 1.0 the negative is ignored entirely; it exists here for future
higher-cfg runs without the Lightning LoRA.
"""
import json
import os
import sys
import time
import urllib.request
import uuid

ROOT = os.path.join(os.path.dirname(__file__), "..")
COMFY = "http://127.0.0.1:8188"
WORKFLOW = os.path.join(ROOT, "workflows", "comfy_qwen_t2i_gguf_api.json")
OUTPUT_DIR = os.path.join(ROOT, "tools", "ComfyUI", "output")
# The office's render-wins rule (llm_router.generate checks this flag and
# answers "briefly offline" instead of evicting ComfyUI mid-job). A Qwen
# render is 6-14 min -- unflagged, the first agent chat/reflection KILLS it
# (measured twice, 2026-08-29). Same file+format comfy_image uses.
RENDER_FLAG = os.path.join(ROOT, "data", "video_rendering.flag")


_MY_FLAG_TOKEN = None


def _flag(on):
    """Set/clear the render flag -- but only clear OUR OWN flag. An
    unconditional clear took down another process's render 2026-08-29
    (my finally dropped the flag mid-batch; an idle reflection then
    evicted ComfyUI). The token check makes concurrent renderers safe."""
    global _MY_FLAG_TOKEN
    try:
        if on:
            _MY_FLAG_TOKEN = str(time.time())
            with open(RENDER_FLAG, "w") as fh:
                fh.write(_MY_FLAG_TOKEN)
        else:
            try:
                current = open(RENDER_FLAG).read().strip()
            except OSError:
                return
            if current == _MY_FLAG_TOKEN:
                os.remove(RENDER_FLAG)
    except OSError:
        pass


def build(prompt, prefix, seed, width, height, negative):
    wf = json.load(open(WORKFLOW, encoding="utf-8"))
    wf["5"]["inputs"]["text"] = prompt
    wf["6"]["inputs"]["text"] = negative
    wf["7"]["inputs"]["width"] = width
    wf["7"]["inputs"]["height"] = height
    wf["8"]["inputs"]["seed"] = seed
    wf["10"]["inputs"]["filename_prefix"] = prefix
    return wf


def run(prompt, prefix="qwen_t2i", seed=None, width=1024, height=1024,
        negative="", timeout=2400):
    seed = seed if seed is not None else int(time.time()) % (2 ** 31)
    wf = build(prompt, prefix, seed, width, height, negative)
    req = urllib.request.Request(
        f"{COMFY}/prompt",
        data=json.dumps({"prompt": wf, "client_id": str(uuid.uuid4())}).encode(),
        headers={"Content-Type": "application/json"})
    _flag(True)
    try:
        try:
            pid = json.loads(urllib.request.urlopen(req, timeout=120).read())["prompt_id"]
        except urllib.error.HTTPError as e:
            # ComfyUI's validation body names the bad node. Never swallow it.
            raise SystemExit(f"ComfyUI rejected the workflow:\n{e.read().decode()[:1200]}")
        print(f"queued {pid}\n  {width}x{height} seed={seed}\n  prompt={prompt[:110]}",
              flush=True)

        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(3)
            try:
                hist = json.loads(urllib.request.urlopen(
                    f"{COMFY}/history/{pid}", timeout=30).read())
            except Exception:
                continue
            if pid not in hist:
                continue
            entry = hist[pid]
            status = entry.get("status", {})
            if status.get("status_str") == "error" or status.get("completed") is False:
                msgs = json.dumps(status.get("messages", []))[:900]
                raise SystemExit(f"render failed: {msgs}")
            for out in entry.get("outputs", {}).values():
                for img in out.get("images", []):
                    path = os.path.join(OUTPUT_DIR, img["filename"])
                    print(f"done -> {path}", flush=True)
                    return path
            if entry.get("outputs"):
                break
        raise SystemExit(f"timed out after {timeout}s")
    finally:
        _flag(False)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    size = sys.argv[3] if len(sys.argv) > 3 else "1024x1024"
    w, h = (int(x) for x in size.lower().split("x"))
    run(sys.argv[1],
        sys.argv[2] if len(sys.argv) > 2 else "qwen_t2i",
        width=w, height=h,
        negative=sys.argv[4] if len(sys.argv) > 4 else "")
