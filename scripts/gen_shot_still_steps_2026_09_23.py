"""Render the saved still fence of a gen'd shot at a chosen step count. Usage: gen_shot_still_steps_2026_09_23.py 02 40"""
import re, sys, json, time, httpx
B = "http://127.0.0.1:8420"
n = sys.argv[1]; steps = int(sys.argv[2])
reply = open(f"data/_gen_shot{n}_reply.txt", encoding="utf-8").read()
img = re.search(r"```image\s*\n(.*?)```", reply, re.S).group(1).strip()
t = time.time()
g = httpx.post(f"{B}/api/generate-image", json={"agent_id": "movie", "prompt": img, "steps": steps}, timeout=7200).json()
print("STILL", round(time.time() - t), "s", json.dumps({k: g.get(k) for k in ("approval_id", "error", "path", "extras")}, default=str), flush=True)
