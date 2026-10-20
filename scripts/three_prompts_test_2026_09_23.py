"""Three-prompt split, end to end: 'gen shot 06' -> image + video fences -> IMAGE -> VIDEO(still_prompt)."""
import re, json, time, httpx
B = "http://127.0.0.1:8420"

def chat(msg):
    t = time.time()
    r = httpx.post(f"{B}/api/chat", json={"agent_id": "movie", "message": msg, "task": True}, timeout=1500).json()
    print(f"[{msg!r}] {round(time.time()-t)}s fell_back={r.get('bonsai_fell_back')} "
          f"image={bool(r.get('image_prompt'))} video={bool(r.get('video_prompt'))} len={len(r.get('reply',''))}", flush=True)
    return r

r0 = chat("shot 06")
print("CLARIFY REPLY:", (r0.get("reply") or "")[:300].replace("\n", " | "), flush=True)
r = chat("gen shot 06")
open("data/_gen_shot06_reply.txt", "w", encoding="utf-8").write(r.get("reply", ""))
img, vid = r.get("image_prompt"), r.get("video_prompt")
print("IMAGE FENCE:", (img or "")[:500].replace("\n", " | "), flush=True)
print("VIDEO FENCE:", (vid or "")[:900].replace("\n", " | "), flush=True)
if not (img and vid):
    raise SystemExit("missing a fence")
t1 = time.time()
g = httpx.post(f"{B}/api/generate-image", json={"agent_id": "movie", "prompt": img}, timeout=7200).json()
print("STILL", round(time.time()-t1), "s", json.dumps({k: g.get(k) for k in ("approval_id", "error", "path", "extras")}, default=str), flush=True)
t2 = time.time()
v = httpx.post(f"{B}/api/generate-video", json={"agent_id": "movie", "prompt": vid, "still_prompt": img}, timeout=7200).json()
print("VIDEO", round(time.time()-t2), "s", json.dumps({k: v.get(k) for k in ("approval_id", "error", "path", "still_approval_id", "detail")}, default=str), flush=True)
