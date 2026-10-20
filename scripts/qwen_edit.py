"""Qwen-Image-Edit runner -- change one named thing in an existing image.

    ./venv/Scripts/python.exe scripts/qwen_edit.py <src.png> "<instruction>" [prefix]
    ./venv/Scripts/python.exe scripts/qwen_edit.py "a.png,b.png" "<instruction>" [prefix]

Sources must already sit in ComfyUI's INPUT ROOT (LoadImage does not list
subfolders). Up to THREE, addressable in the instruction as "image 1",
"image 2", "image 3"; image 1 drives the output aspect ratio.

Why this exists: FLUX Kontext is content-filtered (it silently no-op'd a
nude edit) and non-commercial, so it can never touch B Dubb work. Qwen is
Apache 2.0 and unfiltered -- it replaces Kontext for both tracks.

Prompting rules that decide whether this works at all live in the
qwen-image-edit skill: say what to DO never what to avoid, always add a
preservation clause, one change per pass.
"""
import json
import os
import sys
import time
import urllib.request
import uuid

ROOT = os.path.join(os.path.dirname(__file__), "..")
COMFY = "http://127.0.0.1:8188"
# GGUF by default: the fp8 build is 19GB against ~12.9GB usable VRAM and
# spills 6.7GB to system RAM (~60-80s/step, ~20 min an edit -- measured).
# Q4_K_S is 11.4GiB and FITS, and the Lightning LoRA takes it to 8 steps.
# The fp8 workflow stays on disk as comfy_qwen_edit_api.json for a machine
# with more VRAM (or after a Strix Halo upgrade).
WORKFLOW = os.path.join(ROOT, "workflows", "comfy_qwen_edit_gguf_api.json")
INPUT_DIR = os.path.join(ROOT, "tools", "ComfyUI", "input")
OUTPUT_DIR = os.path.join(ROOT, "tools", "ComfyUI", "output")


def build(sources, instruction, prefix, seed):
    wf = json.load(open(WORKFLOW, encoding="utf-8"))
    wf["4"]["inputs"]["image"] = sources[0]
    wf["5"]["inputs"]["prompt"] = instruction
    wf["8"]["inputs"]["seed"] = seed
    wf["10"]["inputs"]["filename_prefix"] = prefix
    # extra references -> new LoadImage nodes, wired into image2/image3 of
    # BOTH encoders so positive and negative see the same set.
    for i, src in enumerate(sources[1:3], start=2):
        node = str(20 + i)
        wf[node] = {"class_type": "LoadImage", "inputs": {"image": src}}
        wf["5"]["inputs"][f"image{i}"] = [node, 0]
        wf["6"]["inputs"][f"image{i}"] = [node, 0]
    return wf


def run(sources, instruction, prefix="qwen_edit", seed=None, timeout=2400):
    # 2400s, not 900 (2026-08-28): on the fp8 build the model does not fit
    # 16GB, spills ~6.7GB to system RAM and runs ~60-80s PER STEP -- a
    # 20-step edit is ~20-25 min. The script timing out while ComfyUI was
    # still happily sampling looked like a failure and was not. The GGUF
    # Q4_K_S build fits and should bring this back to minutes.
    for s in sources:
        if not os.path.isfile(os.path.join(INPUT_DIR, s)):
            raise SystemExit(f"not in ComfyUI input root: {s}")
    seed = seed if seed is not None else int(time.time()) % (2 ** 31)
    wf = build(sources, instruction, prefix, seed)
    req = urllib.request.Request(
        f"{COMFY}/prompt",
        data=json.dumps({"prompt": wf, "client_id": str(uuid.uuid4())}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        pid = json.loads(urllib.request.urlopen(req, timeout=120).read())["prompt_id"]
    except urllib.error.HTTPError as e:
        # ComfyUI returns the validation error body -- it names the bad node,
        # which is the whole diagnosis. Never swallow it.
        raise SystemExit(f"ComfyUI rejected the workflow:\n{e.read().decode()[:1200]}")
    print(f"queued {pid}\n  src={sources}\n  edit={instruction[:110]}", flush=True)

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


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    srcs = [s.strip() for s in sys.argv[1].split(",") if s.strip()]
    run(srcs, sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "qwen_edit")
