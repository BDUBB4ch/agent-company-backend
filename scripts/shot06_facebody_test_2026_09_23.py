"""Ask Elliot for SHOT 06 through the numbered shot path, render its still (face + body refs only)."""
import re, json, time, httpx
B = "http://127.0.0.1:8420"
t0 = time.time()
r = httpx.post(f"{B}/api/chat", json={"agent_id": "movie", "message": "shot 06", "task": True}, timeout=1200).json()
reply = r.get("reply", "")
open("data/_shot06_reply.txt", "w", encoding="utf-8").write(reply)
m = re.search(r"```image\s*\n(.*?)```", reply, re.S)
print("elliot", round(time.time() - t0), "s fell_back", r.get("bonsai_fell_back"), "fence", bool(m), flush=True)
if not m:
    raise SystemExit("no fence")
print("FENCE:", m.group(1).strip()[:700].replace("\n", " | "), flush=True)
t1 = time.time()
g = httpx.post(f"{B}/api/generate-image", json={"agent_id": "movie", "prompt": m.group(1).strip()}, timeout=7200).json()
print("render", round(time.time() - t1), "s", json.dumps({k: g.get(k) for k in ("approval_id", "error", "path", "extras")}, default=str), flush=True)
