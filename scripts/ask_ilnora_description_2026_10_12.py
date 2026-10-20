import os, json, time, httpx
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ilnora_description_2026-10-12.txt")
msg = "Your Wolf's Blood video is done. Give me the description for it."
r = httpx.post("http://127.0.0.1:8420/api/chat", json={"agent_id": "ilnora", "message": msg, "task": True, "office": True, "personal": False}, timeout=2400)
j = r.json() if r.status_code == 200 else {"reply": r.text[:300]}
open(OUT, "w", encoding="utf-8").write(f"tools={j.get('tool_calls')} fell_back={j.get('bonsai_fell_back')}\n\n{j.get('reply')}\n")
