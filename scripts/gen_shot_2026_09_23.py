"""'gen shot NN' through Elliot -> still (IMAGE) -> clip (VIDEO from that still). Usage: gen_shot_2026_09_23.py 02"""
import re, sys, json, time, httpx
B = "http://127.0.0.1:8420"
n = sys.argv[1] if len(sys.argv) > 1 else "02"
t = time.time()
r = httpx.post(f"{B}/api/chat", json={"agent_id": "movie", "message": f"gen shot {n}", "task": True}, timeout=1500).json()
open(f"data/_gen_shot{n}_reply.txt", "w", encoding="utf-8").write(r.get("reply", ""))
img, vid = r.get("image_prompt"), r.get("video_prompt")
print(f"elliot {round(time.time()-t)}s fell_back={r.get('bonsai_fell_back')} image={bool(img)} video={bool(vid)}", flush=True)
print("IMAGE:", (img or "")[:600].replace("\n", " | "), flush=True)
print("VIDEO:", (vid or "")[:900].replace("\n", " | "), flush=True)
if not (img and vid):
    raise SystemExit("missing a fence")
t = time.time()
g = httpx.post(f"{B}/api/generate-image", json={"agent_id": "movie", "prompt": img}, timeout=7200).json()
print("STILL", round(time.time()-t), "s", json.dumps({k: g.get(k) for k in ("approval_id", "error", "path")}, default=str), flush=True)
t = time.time()
v = httpx.post(f"{B}/api/generate-video", json={"agent_id": "movie", "prompt": vid, "still_prompt": img}, timeout=7200).json()
print("VIDEO", round(time.time()-t), "s", json.dumps({k: v.get(k) for k in ("approval_id", "error", "path", "detail")}, default=str), flush=True)
