"""VIDEO step only, from the saved 'gen shot 06' reply: LTX fence as prompt, image fence as still_prompt."""
import re, json, time, httpx
B = "http://127.0.0.1:8420"
reply = open("data/_gen_shot06_reply.txt", encoding="utf-8").read()
img = re.search(r"```image\s*\n(.*?)```", reply, re.S).group(1).strip()
vid = re.search(r"```video\s*\n(.*?)```", reply, re.S).group(1).strip()
t2 = time.time()
v = httpx.post(f"{B}/api/generate-video", json={"agent_id": "movie", "prompt": vid, "still_prompt": img}, timeout=7200).json()
print("VIDEO", round(time.time() - t2), "s", json.dumps({k: v.get(k) for k in ("approval_id", "error", "path", "still_approval_id", "detail")}, default=str), flush=True)
