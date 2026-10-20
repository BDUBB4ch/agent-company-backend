"""Second live check batch (2026-10-12): Ilnora's new work ledger, then Sophie's banner question again."""
import os, json, time, httpx
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "live_checks2_2026-10-12.txt")
def chat(agent, msg):
    t = time.time()
    r = httpx.post("http://127.0.0.1:8420/api/chat", json={"agent_id": agent, "message": msg, "task": True, "office": True, "personal": False}, timeout=2400)
    j = r.json() if r.status_code == 200 else {"reply": r.text[:300]}
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(f"\n=== {agent} ({time.time()-t:.0f}s) ===\nASK: {msg}\ntools={j.get('tool_calls')} fell_back={j.get('bonsai_fell_back')}\nREPLY:\n{j.get('reply')}\n")
chat("ilnora", "What videos have you planned, and what have you already written and made?")
chat("engineer", "What does the red banner on the dashboard say right now? Is it real?")
open(OUT, "a").write("\nDONE\n")
