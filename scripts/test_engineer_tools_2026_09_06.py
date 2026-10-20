"""Battery for Sophie's capability layer (2026-09-06): search, chunked reads,
the widened roots, command gating, whole-file write + undo through codefix,
and the update board's shapes. Run after ANY change to engineer_tools.py,
codefix.propose_write, read_project_file.read_file or the _SAFE list.

    ../venv/Scripts/python.exe scripts/test_engineer_tools_2026_09_06.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))

import codefix  # noqa: E402
import engineer_tools as et  # noqa: E402
import memory  # noqa: E402
import read_project_file as rpf  # noqa: E402

fails = 0


def check(label, cond, detail=""):
    global fails
    print(("PASS " if cond else "FAIL ") + label + (f"  -- {detail}" if detail and not cond else ""))
    if not cond:
        fails += 1


# ---- search + reads ---------------------------------------------------------
r = et.search_project(r"def propose_write", "backend", "*.py")
check("search finds propose_write in codefix", any(h["file"].endswith("codefix.py") for h in r.get("hits", [])), str(r)[:200])
check("search refuses outside root", "error" in et.search_project("x", r"C:\Windows"))

r = rpf.read_file(os.path.join(ROOT, "backend", "main.py"), start_line=4000, max_lines=5)
check("chunked read: start/end/total", r.get("start_line") == 4000 and r.get("end_line") == 4004 and r.get("total_lines", 0) > 4004, str({k: r.get(k) for k in ("start_line", "end_line", "total_lines")}))
check("chunked read names next start_line", "start_line=4005" in (r.get("note") or ""), r.get("note"))
r = rpf.read_file(os.path.join(ROOT, "backend", "main.py"))
check("big file read reports partial", r.get("truncated") and "PARTIAL" in r.get("note", ""), r.get("note"))
check("dashboard readable", "content" in rpf.read_file(os.path.join(ROOT, "..", "AgentDashboard", "app.js"), 1, 3))
check("comfy rig readable", "content" in rpf.read_file(os.path.join(et.COMFY_DIR, "main.py"), 1, 3))
check("MyStudio readable", "content" in rpf.read_file(os.path.join(ROOT, "..", "MyStudio.html"), 1, 3))
check("venv NOT readable via codefix", codefix._resolve(os.path.join(ROOT, "venv", "pyvenv.cfg"))[0] is None)

# ---- command gating ---------------------------------------------------------
safe = [r"python scripts\test_job_routing.py", "git status", "python -m pip show fastapi",
        "node --check app.js", "dir", r"python -m py_compile backend\updates.py", r"python scripts\preflight_check.py"]
unsafe = ["python -m pip install requests", r"python scripts\apply_x.py", "schtasks /create /tn x", "del main.py"]
for c in safe:
    check(f"safe: {c}", et.is_safe_command(c))
for c in unsafe:
    check(f"not safe: {c}", not et.is_safe_command(c))
check("torch pip refused", et._pip_install_check("python -m pip install torch") is not None)
check("custom index refused", et._pip_install_check("pip install foo --index-url http://x") is not None)
check("plain pip allowed to queue", et._pip_install_check("pip install requests==2.32.0") is None)
check("chain refused", et.run_command("echo hi && dir")["status"] == "refused")
r = et.run_command(r"python -m py_compile backend\updates.py")
check("py_compile runs now", r["status"] == "ok", str(r)[:200])
r = et.run_command("node --check app.js", cwd="dashboard")
check("node --check runs in dashboard cwd", r["status"] == "ok", str(r)[:200])
r = et.run_command(r"python scripts\test_job_routing.py")
check("routing battery runs via run_command", r["status"] == "ok" and "22" in r["output"], r.get("output", "")[-200:])

# ---- queued command round trip ----------------------------------------------
r = et.run_command("python -m pip show pip-does-not-matter", why="battery")  # safe -> runs now
check("pip show is safe", r["status"] in ("ok", "nonzero_exit"))
r = et.run_command(r"python scripts\_battery_no_such_script.py", why="battery queue test")
check("unsafe command queues", r["status"] == "queued" and r.get("approval_id"), str(r)[:200])
qid = r.get("approval_id")
if qid:
    memory.decide_approval(qid, True)
    res = et.run_approved(qid)
    check("approved command runs and records", res.get("status") in ("ok", "nonzero_exit", "failed"), str(res)[:200])
    rows = [x for x in et.task_rows(5) if x["id"] == qid]
    check("task row visible with output", rows and rows[0].get("dispatch_status"), str(rows)[:200])
    with memory.get_db() as conn:
        conn.execute("DELETE FROM approvals WHERE id=?", (qid,))

# ---- whole-file write + undo -----------------------------------------------
target = os.path.join(ROOT, "data", "_battery_new_module.py")
if os.path.exists(target):
    os.remove(target)
r = codefix.propose_write(target, "def hello():\n    return 3\n", "battery: new file", "none; undo removes it", apply_now=True, reason="new file")
check("new file auto-applies", r.get("status") == "auto_applied" and os.path.isfile(target), str(r)[:200])
fid = r.get("approval_id")
r2 = codefix.propose_write(target, "def hello():\n    return 4\n", "battery: small rewrite", "none", apply_now=True, reason="simple")
check("small rewrite auto-applies", r2.get("status") == "auto_applied" and "return 4" in open(target).read(), str(r2)[:200])
big = "\n".join(f"x{i} = {i}" for i in range(40)) + "\n"
import watch  # noqa: E402
_real_vital = watch.vital_conditions
watch.vital_conditions = lambda: []          # the gate must judge SIZE here, not today's office state
r3 = codefix.propose_write(target, big, "battery: big rewrite", "none", apply_now=True, reason="big")
watch.vital_conditions = _real_vital
check("big rewrite is QUEUED not applied", r3.get("status") == "queued" and "return 4" in open(target).read(), str(r3)[:200])
bad = codefix.propose_write(os.path.join(ROOT, "data", "_battery_bad.py"), "def (:\n", "x", "x")
check("unparseable python refused", bad.get("status") == "refused")
u2 = codefix.undo_fix(r2["approval_id"])
check("undo rewrite restores return 3", u2.get("status") == "undone" and "return 3" in open(target).read(), str(u2)[:200])
u1 = codefix.undo_fix(fid)
check("undo creation removes the file", u1.get("status") == "undone" and not os.path.exists(target), str(u1)[:200])
with memory.get_db() as conn:
    for aid in (fid, r2.get("approval_id"), r3.get("approval_id")):
        if aid:
            conn.execute("DELETE FROM approvals WHERE id=?", (aid,))
codefix.refresh_journal()

# ---- updates shapes ---------------------------------------------------------
import updates  # noqa: E402
st = updates.result()
check("updates.result has items + legacy keys", "items" in st and "model_update_available" in st)
check("apply refuses unknown item", updates.apply("nope:x")["status"] == "refused")
check("apply refuses manual item", updates.apply("ollama-app")["status"] == "refused")
check("summary line", updates.summary_line().startswith("updates"))
check("check_updates status shape", "items" in et.check_updates("status"))

print(f"\n{'ALL PASS' if not fails else str(fails) + ' FAILED'}")
sys.exit(1 if fails else 0)
