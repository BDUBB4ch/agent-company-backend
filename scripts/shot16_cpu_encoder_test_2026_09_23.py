"""Ask Elliot for SHOT 16, render its still through /api/generate-image (group door, CPU encoder)."""
import re, json, time, httpx
B = "http://127.0.0.1:8420"
t0 = time.time()
r = httpx.post(f"{B}/api/chat", json={"agent_id": "movie", "message": "shot 16", "task": True},
               timeout=900).json()
reply = r.get("reply", "")
m = re.search(r"```image\s*\n(.*?)```", reply, re.S)
open("data/_shot16_reply.txt", "w", encoding="utf-8").write(reply)
print("elliot", round(time.time() - t0), "s  fell_back", r.get("bonsai_fell_back"), "fence", bool(m), flush=True)
if not m:
    raise SystemExit("no fence")
t1 = time.time()
g = httpx.post(f"{B}/api/generate-image", json={"agent_id": "movie", "prompt": m.group(1).strip()},
               timeout=7200).json()
print("render", round(time.time() - t1), "s", json.dumps({k: g.get(k) for k in
      ("approval_id", "error", "file_path", "extras")}, default=str), flush=True)
