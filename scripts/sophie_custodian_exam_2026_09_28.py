"""Sophie's custodian exam (Barry, 2026-09-28: "shes the custodian of it all.
she need to be on point" / "she is also security").

Nine real questions across the build, sent as task turns (task:true, not logged
to her thread). Answers + tools saved to data/sophie_exam_2026-09-28.json for
grading against the code.
"""
import json
import time
import httpx

QUESTIONS = [
    ("reliability", "If one agent's long job makes Bonsai time out, what happens to the other agents now? Be exact about what counts toward the breaker."),
    ("restart", "Walk me through restarting the backend safely, step by step."),
    ("film", "Where does Elliot's live EP1 script live, and are there backups of it?"),
    ("inbox", "Derek wrote me an office note at 7pm on a Saturday. Why wouldn't his dot light up, and when will it?"),
    ("clock", "What are the office hours, and does that stop me getting work done on a Sunday?"),
    ("fallback", "If Bonsai is down, which model answers for you and for the others, and what can those backup models not do?"),
    ("security-live", "Is anything on this PC exposed to the network right now? Check, don't guess."),
    ("security-incident", "What would you do if your watch found a new local administrator account on this PC?"),
    ("security-code", "Are there any security gaps in the office's own code right now? Look before you answer."),
]

out = []
for key, q in QUESTIONS:
    t0 = time.time()
    try:
        r = httpx.post("http://127.0.0.1:8420/api/chat",
                       json={"agent_id": "engineer", "message": q, "task": True}, timeout=1500)
        d = r.json()
        out.append({"key": key, "q": q, "reply": d.get("reply"), "tools": d.get("tool_calls"),
                    "fell_back": d.get("bonsai_fell_back"), "secs": round(time.time() - t0)})
    except Exception as e:  # noqa: BLE001
        out.append({"key": key, "q": q, "error": f"{type(e).__name__}: {e}", "secs": round(time.time() - t0)})
    print(key, out[-1].get("secs"), "s", "ERROR" if "error" in out[-1] else "", flush=True)
    json.dump(out, open("data/sophie_exam_2026-09-28.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("done")
