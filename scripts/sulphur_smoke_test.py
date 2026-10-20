"""Sulphur 2 smoke test -- one short clip with a spoken line, through the
new comfy_t2v_sulphur_api.json workflow (LTX-2.3 pipeline, Sulphur weights).

    ./venv/Scripts/python.exe scripts/sulphur_smoke_test.py

Raises the render flag (the office's render-wins rule) so agent chats and
idle reflections answer "briefly offline" instead of killing the render --
the unflagged version of this test died twice on 2026-08-29 to exactly that.
Dialogue is quoted-line-in-prose: the LTX grammar proven to produce speech.
"""
import asyncio
import json
import os
import sys
import time
import urllib.request
import uuid

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
import comfy_image  # noqa: E402
import llm_router  # noqa: E402

WORKFLOW = os.path.join(ROOT, "workflows", "comfy_t2v_sulphur_api.json")
COMFY = "http://127.0.0.1:8188"

PROMPT = (
    "A weathered man in a dark jacket stands in a dim warehouse doorway at "
    "night, rain dripping off the frame. He looks over his shoulder, then "
    'says in a low, wary voice, "Somebody got here before us." He steps '
    "inside and the camera follows him slowly into the darkness."
)


def main():
    # THE LESSON OF 2026-08-29, third dead render: a resident Bonsai server
    # shares the 16GB card with the render, everything spills, sampling
    # crawls at ~zero progress and eventually dies. The office's own render
    # path evicts LLMs first (one-big-thing rule) -- standalone scripts
    # must do the same.
    asyncio.run(llm_router.unload_all_models())
    print("LLMs evicted", flush=True)
    ok = asyncio.run(comfy_image.ensure_running())
    print("comfy up:", ok, flush=True)
    if not ok:
        raise SystemExit("ComfyUI would not start")

    wf = json.load(open(WORKFLOW, encoding="utf-8"))
    wf["266"]["inputs"]["value"] = PROMPT
    data = json.dumps({"prompt": wf, "client_id": str(uuid.uuid4())}).encode()
    req = urllib.request.Request(f"{COMFY}/prompt", data=data,
                                 headers={"Content-Type": "application/json"})
    comfy_image._set_render_flag()
    try:
        try:
            pid = json.loads(urllib.request.urlopen(req, timeout=120).read())["prompt_id"]
        except urllib.error.HTTPError as e:
            raise SystemExit("REJECTED: " + e.read().decode()[:1500])
        print("queued", pid, flush=True)

        deadline = time.time() + 3600
        while time.time() < deadline:
            time.sleep(15)
            try:
                hist = json.loads(urllib.request.urlopen(
                    f"{COMFY}/history/{pid}", timeout=30).read())
            except Exception as e:
                print("poll:", str(e)[:60], flush=True)
                continue
            if pid not in hist:
                continue
            entry = hist[pid]
            st = entry.get("status", {})
            if st.get("status_str") == "error":
                raise SystemExit("FAILED: " + json.dumps(st.get("messages", []))[:1200])
            if entry.get("outputs"):
                for out in entry["outputs"].values():
                    for kind in ("images", "gifs", "video", "videos"):
                        for f in out.get(kind, []):
                            print("OUTPUT:", f.get("filename"), flush=True)
                print("SMOKE_TEST_DONE", flush=True)
                return
        raise SystemExit("timed out after 3600s")
    finally:
        comfy_image._clear_render_flag()


if __name__ == "__main__":
    main()
