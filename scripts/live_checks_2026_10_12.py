"""Live confidence checks before Ilnora builds (Barry 2026-10-12: 'do the checks'). One Elliot turn, one Sophie turn.
Writes replies + tool log summary to data/live_checks_2026-10-12.txt. Test turns are removed from the threads after."""
import os, sys, json, time, httpx
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "live_checks_2026-10-12.txt")
def chat(agent, msg, task):
    t = time.time()
    r = httpx.post("http://127.0.0.1:8420/api/chat", json={"agent_id": agent, "message": msg, "task": task, "personal": False}, timeout=2400)
    j = r.json() if r.status_code == 200 else {"reply": r.text[:300]}
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(f"\n=== {agent} ({time.time()-t:.0f}s) ===\nASK: {msg}\n{json.dumps({k: j.get(k) for k in j if k != 'reply'}, default=str)[:600]}\nREPLY:\n{j.get('reply')}\n")
chat("movie", "shot 28", False)
chat("engineer", "What is the red banner on the dashboard saying right now? Check it against the traces and tell me if it is real.", True)
with open(OUT, "a") as f: f.write("\nDONE\n")
