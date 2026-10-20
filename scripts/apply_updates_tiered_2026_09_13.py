"""Drive the UPDATE BOARD through its own door, one item at a time, and wait for
each job -- exactly what Sophie's `check_updates apply:<id>` does after Barry's
approval, so the procedure she learns is the one this script runs.

    python scripts/apply_updates_tiered_2026_09_13.py tier1
    python scripts/apply_updates_tiered_2026_09_13.py tier2
    python scripts/apply_updates_tiered_2026_09_13.py comfyui
    python scripts/apply_updates_tiered_2026_09_13.py pip:httpx pip:lxml   # any ids

Tiers (2026-09-13 board):
  tier1  = every pip item EXCEPT the web stack (small bumps, one batch)
  tier2  = fastapi / starlette / pydantic / pydantic_core / uvicorn -- the four
           that move together and can break the backend; done as a group so a
           mismatched pair never runs live.
Never touches: torch family (the board refuses), the Ollama app (manual, AMD
bundle build), anything mid-render (the board refuses).
Restart the backend after a tier (preflight first) -- pip installs do not
reload a running process.
"""
import json
import sys
import time
import urllib.request

API = "http://127.0.0.1:8420"
WEB_STACK = {"pip:fastapi", "pip:starlette", "pip:pydantic", "pip:pydantic_core", "pip:uvicorn"}


def _get(path):
    with urllib.request.urlopen(API + path, timeout=120) as r:
        return json.load(r)


def _post(path, body):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def board():
    d = _get("/api/updates")
    return [i for i in d.get("items", []) if i.get("update_available") or i.get("available")]


def wait_job(job_id, timeout=1800):
    t0 = time.time()
    while time.time() - t0 < timeout:
        for j in _get("/api/updates/jobs").get("jobs", []):
            if j["id"] == job_id and j["status"] in ("done", "failed"):
                return j
        time.sleep(3)
    return {"id": job_id, "status": "timeout", "log": []}


def main(args):
    avail = board()
    ids = [i["id"] for i in avail]
    want = []
    for a in args:
        if a == "tier1":
            want += [i for i in ids if i.startswith("pip:") and i not in WEB_STACK]
        elif a == "tier2":
            want += [i for i in ids if i in WEB_STACK]
        else:
            want.append(a)
    print(f"{len(want)} item(s):", ", ".join(want))
    results = []
    for iid in want:
        # The board marks a job "done" and THEN re-scans pip (~20 s) in the same
        # thread; apply() refuses "one at a time" until that thread ends. Wait it out.
        for _ in range(60):
            r = _post("/api/updates/apply", {"item": iid})
            if "still running" not in (r.get("why") or ""):
                break
            time.sleep(5)
        if r.get("status") != "started":
            print(f"  {iid}: REFUSED -- {r.get('why')}")
            results.append((iid, "refused"))
            continue
        j = wait_job(r["job"])
        tail = (j.get("log") or ["(no log)"])[-1]
        print(f"  {iid}: {j['status']} -- {tail[:160]}")
        results.append((iid, j["status"]))
    print("\nSUMMARY:", {s: sum(1 for _, x in results if x == s) for s in ("done", "failed", "refused", "timeout")})
    bad = [i for i, s in results if s != "done"]
    if bad:
        print("NOT DONE:", ", ".join(bad))


if __name__ == "__main__":
    main(sys.argv[1:] or ["tier1"])
