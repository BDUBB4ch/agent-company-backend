"""HIRE SMOKE TEST -- prove a new agent is a real seat before Barry meets it.

Barry, 2026-09-19: "we need to get this solid. I dont want these issues with
the next agent i hire."

THE PROBLEM THIS EXISTS FOR. A hire lives in CUSTOM_AGENTS, not AGENTS, and
this codebase is full of honest-looking code that walks the built-in nine. Every
one of those is a SILENT failure for a hire -- no exception, no log line, just a
window that renders empty or a loop that never picks them. Found the hard way:
  * seven read endpoints 404'd every hire (2026-09-19b)
  * the inbox never counted a hire's notes (2026-09-19c)
  * the model switch never listed a hire (2026-09-19c)
  * the reflection, stray-thought and social loops never picked one, so a hire
    had no inner life at all (2026-09-19c)

So: hire a throwaway agent, drive everything a real seat uses, delete it, and
print one PASS/FAIL line each. No GPU -- nothing here runs a generation, so it
is safe to run any time, including while a render is going.

    ../venv/Scripts/python.exe scripts/hire_smoke_test_2026_09_19.py

Run it after ANY change that touches the roster, and after hiring for real.
"""
import json
import os
import sys
import shutil
import sqlite3
import urllib.error
import urllib.request

BASE = os.environ.get("OFFICE_URL", "http://127.0.0.1:8420")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE_NAME = "Smoketest Probe"
PROBE_ID = None          # filled in by the hire call
PROBE_OFFICE = None

results: list[tuple[bool, str, str]] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    results.append((bool(ok), label, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  -- {detail}" if detail else ""))
    return bool(ok)


def call(method: str, path: str, body=None, expect_json=True):
    """Returns (status, parsed_or_text). Never raises on an HTTP error --
    a 404 IS the finding here, not a crash."""
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(raw) if expect_json and raw else raw)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:200]
    except Exception as e:  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"


def cleanup(agent_id: str, office: str):
    """Remove every trace of the probe. Direct DB work on purpose -- there is
    still no fire/delete endpoint (flagged 2026-09-18d)."""
    db = os.path.join(ROOT, "data", "brain.db")
    try:
        with sqlite3.connect(db) as c:
            for sql, args in [
                ("delete from custom_agents where agent_id=?", (agent_id,)),
                ("delete from conversations where agent_id=?", (agent_id,)),
                ("delete from facts where category=?", (f"private:{office}",)),
                ("delete from agent_domains where agent_id=?", (agent_id,)),
                ("delete from agent_knows where office_name=?", (office,)),
            ]:
                try:
                    c.execute(sql, args)
                except sqlite3.OperationalError:
                    pass       # table may not exist in an older DB
            c.commit()
    except Exception as e:  # noqa: BLE001
        print(f"  (cleanup db: {e})")
    for path in [os.path.join(ROOT, "personas", f"{office}.md"),
                 os.path.join(ROOT, "personalities", f"{office}.md")]:
        if os.path.exists(path):
            os.remove(path)
    for folder in [os.path.join(ROOT, "drop", PROBE_NAME.split()[0]),
                   os.path.join(ROOT, "drop", office),
                   os.path.join(ROOT, "data", "agent_files", office)]:
        if os.path.isdir(folder):
            shutil.rmtree(folder, ignore_errors=True)


def main() -> int:
    global PROBE_ID, PROBE_OFFICE
    print(f"HIRE SMOKE TEST -- {BASE}\n")

    st, _ = call("GET", "/api/agents")
    if st != 200:
        print("backend is not answering -- start it first.")
        return 2

    print("hiring a throwaway agent")
    st, hire = call("POST", "/api/agents/hire", {
        "name": PROBE_NAME,
        "role": "Smoke Test",
        "job_description": "A throwaway probe agent. Delete me.",
        "persona": "You are a probe. Answer in one line.",
        "personality": "Quiet.",
    })
    if st != 200 or not isinstance(hire, dict):
        print(f"  FAIL  hire endpoint returned {st}: {str(hire)[:200]}")
        return 2
    PROBE_ID = hire.get("agent_id") or hire.get("id")
    PROBE_OFFICE = hire.get("office_name") or PROBE_ID
    print(f"  hired {PROBE_ID} (office {PROBE_OFFICE})\n")

    try:
        # --- the roster ---------------------------------------------------
        st, agents = call("GET", "/api/agents")
        ids = [a.get("id") for a in agents] if isinstance(agents, list) else []
        check(PROBE_ID in ids, "/api/agents lists the hire")
        check(len(ids) >= 10 and all(
            b in ids for b in ("cio", "operations", "business", "legal", "marketing",
                               "creative", "movie", "engineer", "taliyah")),
            "the nine are still all present", f"{len(ids)} seats")

        st, models = call("GET", "/api/agents/models")
        rows = models.get("agents") if isinstance(models, dict) else models
        mids = [r.get("id") for r in rows] if isinstance(rows, list) else []
        check(PROBE_ID in mids, "/api/agents/models lists the hire",
              "so Barry can see and change its model")

        # --- the read endpoints that 404'd on 2026-09-19 -------------------
        for path, label in [
            (f"/api/agents/{PROBE_ID}/mind", "mind (home window)"),
            (f"/api/agents/{PROBE_ID}/work-thread", "work thread (office window)"),
            (f"/api/agents/{PROBE_ID}/dms", "dms"),
            (f"/api/brain/graph/{PROBE_ID}", "brain graph"),
            (f"/api/agents/{PROBE_ID}/persona-additions", "persona additions"),
            (f"/api/agents/{PROBE_ID}/pictures", "pictures gallery"),
        ]:
            st, _b = call("GET", path)
            check(st == 200, f"GET {label}", f"HTTP {st}")

        st, _ = call("POST", f"/api/inbox/{PROBE_ID}/read?channel=personal")
        check(st == 200, "inbox read-marker accepts the hire", f"HTTP {st}")

        # --- the doors Barry uses ------------------------------------------
        st, _ = call("POST", f"/api/agents/{PROBE_ID}/teach",
                     {"kind": "knowledge", "title": "probe note",
                      "text": "USE WHEN: probe smoke test.\n\nNothing real."})
        check(st == 200, "teach panel reaches the hire", f"HTTP {st}")

        first = PROBE_NAME.split()[0]
        folder = os.path.join(ROOT, "drop", first)
        check(os.path.isdir(folder), "teach-drop folder exists at birth",
              os.path.relpath(folder, ROOT))

        st, audit = call("GET", f"/api/agents/{PROBE_ID}/owner-audit")
        check(st == 200, "birth audit runs", f"HTTP {st}")

        st, _ = call("POST", f"/api/agents/{PROBE_ID}/clear-thread")
        check(st == 200, "clear-thread works", f"HTTP {st}")

        # --- the loops that own their inner life ---------------------------
        sys.path.insert(0, os.path.join(ROOT, "backend"))
        import memory as _m            # noqa: E402
        import reflect as _r           # noqa: E402
        import social as _s            # noqa: E402

        knows = _m.knows_about(PROBE_OFFICE) or []
        check("owner" not in knows and "team" not in knows,
              "a fresh hire knows nothing of his world", f"knows={knows or 'nothing'}")
        check(PROBE_ID not in _r.life_roster(),
              "...so it is correctly OUT of the reflection loop")
        check(PROBE_ID not in _s.social_roster(),
              "...and OUT of the group chat")

        _m.grant_knows_about(PROBE_OFFICE, "owner", "smoke test")
        _m.grant_knows_about(PROBE_OFFICE, "team", "smoke test")
        check(PROBE_ID in _r.life_roster(),
              "granted 'owner' -> it reflects, keeps a diary, can write him")
        check(PROBE_ID in _s.social_roster(),
              "granted 'team'  -> it joins group chat and DMs")

        # --- the prompt it actually runs on --------------------------------
        import agents as _a            # noqa: E402
        prompt = _a.build_hired_agent_prompt(PROBE_NAME, "Smoke Test",
                                             "A throwaway probe.",
                                             business_context=False)
        check("## How you answer" in prompt,
              "hire prompt carries the concise-answer rule")
        for word in ("Barry", "B Dubb", "Bionova", "PID", "Gotcho"):
            if word.lower() in prompt.lower():
                check(False, "blank-slate prompt names his world", word)
                break
        else:
            check(True, "blank-slate prompt names none of his world")

    finally:
        print("\ncleaning up the probe")
        cleanup(PROBE_ID, PROBE_OFFICE)
        st, agents = call("GET", "/api/agents")
        ids = [a.get("id") for a in agents] if isinstance(agents, list) else []
        print(f"  probe still listed: {PROBE_ID in ids} (a restart clears the live roster)")

    bad = [r for r in results if not r[0]]
    print(f"\n{len(results) - len(bad)}/{len(results)} checks passed")
    for _ok, label, detail in bad:
        print(f"  FAIL  {label}  {detail}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
