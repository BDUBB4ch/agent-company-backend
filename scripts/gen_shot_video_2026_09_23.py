"""VIDEO step for a gen'd shot at a chosen length, waiting for the still first. Usage: gen_shot_video_2026_09_23.py 02 10"""
import re, sys, json, time, httpx
B = "http://127.0.0.1:8420"
n = sys.argv[1]; dur = int(sys.argv[2]) if len(sys.argv) > 2 else 10
reply = open(f"data/_gen_shot{n}_reply.txt", encoding="utf-8").read()
img = re.search(r"```image\s*\n(.*?)```", reply, re.S).group(1).strip()
vid = re.search(r"```video\s*\n(.*?)```", reply, re.S).group(1).strip()
# wait for the still that is already rendering
while True:
    s = httpx.get(f"{B}/api/generate/status", timeout=30).json()
    if not s.get("busy") and not s.get("video_render_holding_gpu"):
        break
    time.sleep(15)
print("still finished; starting", dur, "s clip", flush=True)
t = time.time()
v = httpx.post(f"{B}/api/generate-video", json={"agent_id": "movie", "prompt": vid, "still_prompt": img, "duration_s": dur}, timeout=7200).json()
print("VIDEO", round(time.time()-t), "s", json.dumps({k: v.get(k) for k in ("approval_id", "error", "path", "detail")}, default=str), flush=True)
