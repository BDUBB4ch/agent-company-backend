"""Standalone GGUF video probe (2026-08-04).

Runs the new comfy_t2v_ltx_gguf_api.json against a locally-started ComfyUI,
completely outside the backend, and reports wall time per phase. Mirrors
comfy_image.generate_video's patching (same node IDs) so a pass here means
the backend integration is a pure path change.

Usage:  python probe_gguf_video.py [seconds]   (default 5)
Assumes no other ComfyUI is listening on 8188 -- kill it first.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
COMFY_DIR = os.path.join(ROOT, "tools", "ComfyUI")
COMFY_PY = os.path.join(COMFY_DIR, "venv", "Scripts", "python.exe")
HOST = "http://127.0.0.1:8188"
WORKFLOW = os.path.join(ROOT, "workflows", "comfy_t2v_ltx_gguf_api.json")

PROMPT = (
    "A slow cinematic dolly-in on a glass greenhouse at golden hour, rows of "
    "leafy plants, warm sunlight streaming through fogged panes, gentle "
    "ambient birdsong and a soft breeze rustling the leaves"
)


def api(path, payload=None, timeout=15):
    req = urllib.request.Request(
        HOST + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def wait_up(deadline_s=180):
    t0 = time.monotonic()
    while time.monotonic() - t0 < deadline_s:
        try:
            api("/system_stats")
            return time.monotonic() - t0
        except Exception:
            time.sleep(2)
    raise SystemExit("ComfyUI never came up -- check data/comfyui_server.log")


def main():
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    log = open(os.path.join(ROOT, "data", "comfyui.log"),
               "a", encoding="utf-8", errors="replace")
    log.write(f"\n--- GGUF probe start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    log.flush()
    proc = subprocess.Popen(
        [COMFY_PY, "main.py", "--listen", "127.0.0.1", "--port", "8188",
         "--use-pytorch-cross-attention", "--reserve-vram", "1.5"],
        cwd=COMFY_DIR, stdout=log, stderr=subprocess.STDOUT,
        env={**os.environ, "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"},
    )
    try:
        boot = wait_up()
        print(f"ComfyUI up in {boot:.1f}s")

        # GGUF node must be registered or the whole graph is rejected.
        nodes = api("/object_info/UnetLoaderGGUF")
        assert "UnetLoaderGGUF" in nodes, "GGUF loader not registered!"
        print("UnetLoaderGGUF registered OK")

        with open(WORKFLOW, encoding="utf-8") as fh:
            wf = json.load(fh)
        wf["266"]["inputs"]["value"] = PROMPT
        wf["225"]["inputs"]["value"] = duration
        wf["237"]["inputs"]["noise_seed"] = 42

        t0 = time.monotonic()
        prompt_id = api("/prompt", {"prompt": wf}, timeout=60)["prompt_id"]
        print(f"queued {prompt_id}, {duration}s clip at 1280x720/25fps...")

        entry = None
        while time.monotonic() - t0 < 3600:
            time.sleep(5)
            try:
                hist = api(f"/history/{prompt_id}")
            except Exception:
                continue
            if prompt_id in hist:
                entry = hist[prompt_id]
                break
        took = time.monotonic() - t0
        if entry is None:
            raise SystemExit("timed out after 60 min")

        status = entry.get("status", {})
        print(f"render finished in {took/60:.1f} min "
              f"(status: {status.get('status_str')})")
        for out in entry.get("outputs", {}).values():
            for vid in out.get("images", []) + out.get("video", []):
                print("output:", os.path.join(COMFY_DIR, "output",
                                              vid.get("subfolder", ""),
                                              vid["filename"]))
        if status.get("status_str") != "success":
            print(json.dumps(status, indent=2)[:2000])
    finally:
        proc.terminate()
        print("ComfyUI probe instance terminated (backend restarts its own on demand)")


if __name__ == "__main__":
    main()
