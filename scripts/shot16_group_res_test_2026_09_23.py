"""Render Elliot's saved SHOT 16 fence (data/_shot16_reply.txt) through the group door at the new 768 vision budget."""
import re, json, time, httpx
B = "http://127.0.0.1:8420"
reply = open("data/_shot16_reply.txt", encoding="utf-8").read()
m = re.search(r"```image\s*\n(.*?)```", reply, re.S)
assert m, "no fence in saved reply"
t1 = time.time()
g = httpx.post(f"{B}/api/generate-image", json={"agent_id": "movie", "prompt": m.group(1).strip()},
               timeout=7200).json()
print("render", round(time.time() - t1), "s", json.dumps({k: g.get(k) for k in
      ("approval_id", "error", "path", "extras")}, default=str), flush=True)
