"""Elliot picks a one-character shot from the live script, writes it, the office renders its still."""
import re, json, time, httpx
B = "http://127.0.0.1:8420"
ask = ("Pick ONE real shot from the script that has exactly ONE character in frame -- nobody else, "
       "not even in the background. Say which shot you chose and why in one line, then do the full "
       "shot ask on it: your stage 1 block and the paste-ready ```image``` fence.")
t0 = time.time()
r = httpx.post(f"{B}/api/chat", json={"agent_id": "movie", "message": ask, "task": True}, timeout=1200).json()
reply = r.get("reply", "")
open("data/_single_shot_reply.txt", "w", encoding="utf-8").write(reply)
m = re.search(r"```image\s*\n(.*?)```", reply, re.S)
print("elliot", round(time.time() - t0), "s fell_back", r.get("bonsai_fell_back"), "tools", r.get("tool_calls"),
      "fence", bool(m), flush=True)
print("HEAD:", reply[:400].replace("\n", " | "), flush=True)
if not m:
    raise SystemExit("no fence")
t1 = time.time()
g = httpx.post(f"{B}/api/generate-image", json={"agent_id": "movie", "prompt": m.group(1).strip()}, timeout=7200).json()
print("render", round(time.time() - t1), "s", json.dumps({k: g.get(k) for k in ("approval_id", "error", "path", "extras")}, default=str), flush=True)
