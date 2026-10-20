"""Resend Barry's failed ask to Elliot (his exact words; the 4 earlier sends died on the context overflow fixed at
13:23) and Sophie's training brief (its 18:00 send collided with the old video schedule). Then exit."""
import os, sys, httpx
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def chat(agent, msg, task):
    r = httpx.post("http://127.0.0.1:8420/api/chat", json={"agent_id": agent, "message": msg, "task": task,
                   "personal": False}, timeout=2400)
    print(agent, r.status_code, len((r.json() or {}).get("reply") or "") if r.status_code == 200 else r.text[:200], flush=True)
chat("movie", "i need you to go meet Ilnora. She will need your help, maybe with some of her work. just ask her", False)
chat("engineer", open(os.path.join(ROOT, "data", "sophie_brief_2026-10-10.md"), encoding="utf-8").read(), True)
