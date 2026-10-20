"""One task turn: Elliot opens render 442 (the still Barry called perfect) and his own 457, compares, keeps a lesson."""
import json, time, httpx
B = "http://127.0.0.1:8420"
ask = ("Barry wants you to study a reference. Open render 442 with look_at_render -- the Vor'Shara still he "
       "called 'absolutely perfect in every way' -- then open your own render 457 (your Shot 02 still). "
       "Compare them as a director: what 442 does with light (one warm source, where it falls, where the "
       "shadow is), with surfaces and materials, with the character's canon details, and why it reads rich "
       "where yours read flat. The prompt that made 442 is now in your approved-prompts shelf (prompt-exemplars). "
       "Then call remember_lesson with the one concrete thing you will do differently in every still prompt "
       "from now on, in your own words. Keep the reply short: what you saw, what you will change.")
t = time.time()
r = httpx.post(f"{B}/api/chat", json={"agent_id": "movie", "message": ask, "task": True}, timeout=1500).json()
print(f"{round(time.time()-t)}s fell_back={r.get('bonsai_fell_back')} tools={r.get('tool_calls')}", flush=True)
print(r.get("reply", ""), flush=True)
