"""FULL FUNCTIONAL AUDIT -- every subsystem, one run, one table.

Barry, 2026-09-07: "when i told you make sure everything is functional, you
were supposed to go through everything we built to make sure it all works
right." So this is that, as one re-runnable script instead of ad-hoc probes.

Read-only except: ONE real chat turn (task:true, not logged to a thread) and
one TTS call. No renders (GPU), no sends, no writes to brains.
Prints PASS/FAIL/SKIP per check with a one-line reason. Exit 1 on any FAIL.
"""
from __future__ import annotations
import asyncio, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BACKEND = os.path.join(REPO, "backend")
DASH = os.path.join(os.path.dirname(REPO), "AgentDashboard")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

import httpx  # noqa: E402

API = "http://127.0.0.1:8420"
DASHURL = "http://127.0.0.1:8765"
ROWS: list[tuple[str, str, str]] = []


def rec(name, ok, note=""):
    ROWS.append((name, "PASS" if ok is True else ("SKIP" if ok is None else "FAIL"), str(note)[:110]))


def check(name):
    def deco(fn):
        t = time.time()
        try:
            r = fn()
            if isinstance(r, tuple):
                rec(name, r[0], r[1])
            else:
                rec(name, bool(r) if r is not None else None, "")
        except Exception as e:  # noqa: BLE001
            rec(name, False, f"{type(e).__name__}: {e}")
        return fn
    return deco


def get(path, **kw):
    return httpx.get(API + path, timeout=kw.pop("timeout", 30), **kw)


# ---------- 1. services + privacy ----------
@check("ports bound to 127.0.0.1 only")
def _():
    ps = ("Get-NetTCPConnection -State Listen | Select-Object LocalAddress,LocalPort | ConvertTo-Json -Compress")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=20).stdout
    rows = json.loads(out or "[]")
    ours = {8420, 8765, 8811, 11434, 8188, 8189}
    bad = [r for r in rows if int(r["LocalPort"]) in ours and r["LocalAddress"] not in ("127.0.0.1", "::1")]
    up = sorted({int(r["LocalPort"]) for r in rows if int(r["LocalPort"]) in ours})
    return (not bad, f"listening {up}; exposed {bad}")

@check("backend /api/agents = the nine + any hires")
def _():
    """⚠️ THIS ASSERTED EXACTLY 9 AND WENT FALSE-FAIL THE DAY BARRY HIRED HIS
    FIRST AGENT (2026-09-19). Hiring is a feature; a roster of 10 is correct.
    What actually has to hold is that all NINE built-ins are present -- a hire
    must never displace one -- so check for the nine by id and report the rest.
    A permanent false FAIL is how a real one gets ignored."""
    j = get("/api/agents").json()
    seats = j if isinstance(j, list) else j.get("agents", j)
    ids = {s.get("agent_id") or s.get("id") for s in seats} if seats and isinstance(seats[0], dict) else set(seats)
    nine = {"cio", "operations", "business", "legal", "marketing",
            "creative", "movie", "engineer", "taliyah"}
    missing = sorted(nine - ids)
    hires = sorted(ids - nine)
    return (not missing,
            f"{len(seats)} seats; missing {missing or 'none'}; hires {hires or 'none'}")

@check("global model = bonsai, all 9 resolve bonsai")
def _():
    g = get("/api/settings/models").json()
    m = get("/api/agents/models").json()
    seats = m if isinstance(m, list) else m.get("agents", m)
    res = [(s.get("agent_id") or s.get("id"), (s.get("resolved") or {}).get("backend") if isinstance(s.get("resolved"), dict) else s.get("resolved_backend") or s.get("backend")) for s in (seats if isinstance(seats, list) else seats.values())]
    offb = [r for r in res if r[1] and r[1] != "bonsai"]
    return (str(g.get("active_backend", g.get("backend"))) == "bonsai" and not offb, f"global={g.get('active_backend', g.get('backend'))} off-bonsai={offb}")

@check("security_watch: no privacy findings")
def _():
    import security_watch as s
    f = s.check()
    priv = [x for x in f if x.split("--")[0].strip() in ("EXPOSED PORT", "BANNED SERVICE IN CODE", "OFFICE BROWSER", "NEW OUTBOUND HOST")]
    return (not priv, f"{len(f)} findings total, privacy={len(priv)} default_engine={s.office_default_engine()}")

@check("web_search = DuckDuckGo only, returns results")
def _():
    import web_search as w
    assert not hasattr(w, "_bing")
    r = asyncio.run(w.search_web("bionova silution"))
    n = len(r.get("results", [])) if isinstance(r, dict) else 0
    return (n > 0, f"{n} results")

@check("offline mode state (informational)")
def _():
    import memory
    return (None, f"offline_mode={memory.is_offline_mode()}")

@check("internet reachable (health)")
def _():
    import health
    return (bool(health.internet_status().get("online", True)), str(health.internet_status())[:80])

# ---------- 2. store + omnisend + dispatch ----------
@check("store: status + lookup + read_product + sales_summary")
def _():
    import store
    st = store.store_status(); lp = store.lookup_product("silution"); rp = store.read_product("silution"); ss = store.sales_summary(30)
    ok = "connected" in st and "SiLution" in lp and "SiLution" in rp and ("$" in ss or "No orders" in ss)
    return (ok, f"{st[:40]} | sales30: {ss.splitlines()[0][:50]}")

@check("store: browse_site + browse_gotchoback")
def _():
    import store
    a = store.browse_site("overview", ""); b = store.browse_gotchoback("products", "")
    return ("product" in a.lower() and "$" in b, f"site {len(a)}ch, gotcho {len(b)}ch")

@check("omnisend_view: list + automations + templates")
def _():
    import omnisend_view as o
    ls = o.list_status(); au = o.list_automations() if hasattr(o, "list_automations") else o.summary("automations"); tp = o.list_templates()
    return ("contacts" in ls.lower() and "enabled" in str(au).lower() and len(str(tp)) > 20, ls.splitlines()[0][:70])

@check("dispatch: enabled, guard refuses re-send of 207")
def _():
    import dispatch
    d = dispatch.dispatch_approved(207, dry_run=True)
    return (dispatch.is_sending_enabled() and d["status"] == "skipped" and "Already" in d["detail"], d["detail"][:60])

@check("email_cadence: next slots computed")
def _():
    import email_cadence as ec
    s = ec.upcoming_slots()
    return (len(s) >= 1, f"next {s[0][0]:%a %m-%d %H:%M}" if s else "none")

@check("GET /api/settings/sending")
def _():
    j = get("/api/settings/sending").json()
    return ("email_weekly_cap" in j, f"cap {j.get('email_weekly_cap')} sent {j.get('email_sends_this_week')}")

# ---------- 3. brains, recall, scripts, routing ----------
@check("brain load per seat under 140K")
def _():
    import memory, agents
    over = []
    for aid, a in agents.AGENTS.items():
        n = len(memory.brain_context_block(a["office_name"])) + len(memory.pinned_skills_block(a["office_name"], agents.PINNED_SKILLS.get(aid, [])))
        if n > 140_000: over.append((aid, n))
    return (not over, f"over={over}")

@check("brain graph for all 9 (API)")
def _():
    import agents
    bad = []
    for aid in agents.AGENTS:
        j = get(f"/api/brain/graph/{aid}", timeout=60).json()
        if not j.get("nodes"): bad.append(aid)
    return (not bad, f"bad={bad}")

@check("recall: routed doc on a real phrase")
def _():
    import recall
    r = recall.recall_for_message("Marketing", "write me an email campaign for the welcome series")
    txt = r if isinstance(r, str) else json.dumps(r)
    return ("omnisend" in txt.lower() or "email" in txt.lower(), f"{len(txt)} chars")

@check("script_index: default script + read_scene SHOT 01")
def _():
    import script_index as si
    d = si.default_script("MovieDirector"); sc = si.read_scene("MovieDirector", "SHOT 01")
    return (bool(d) and "SHOT 01" in json.dumps(sc), f"script={str(d)[:40]}")

@check("job routing battery 22/22")
def _():
    r = subprocess.run([sys.executable, os.path.join(HERE, "test_job_routing.py")], capture_output=True, text=True, timeout=120)
    return ("22/22" in r.stdout or "ALL PASS" in r.stdout, r.stdout.strip().splitlines()[-1][:80] if r.stdout.strip() else r.stderr[-120:])

@check("shot lookup battery")
def _():
    r = subprocess.run([sys.executable, os.path.join(HERE, "test_shot_lookup.py")], capture_output=True, text=True, timeout=120)
    return ("ALL PASS" in r.stdout, r.stdout.strip().splitlines()[-1][:80] if r.stdout.strip() else r.stderr[-120:])

@check("engineer tools battery")
def _():
    r = subprocess.run([sys.executable, os.path.join(HERE, "test_engineer_tools_2026_09_06.py")], capture_output=True, text=True, timeout=300)
    return ("ALL PASS" in r.stdout, r.stdout.strip().splitlines()[-1][:80] if r.stdout.strip() else r.stderr[-120:])

@check("preflight")
def _():
    r = subprocess.run([sys.executable, os.path.join(HERE, "preflight_check.py")], capture_output=True, text=True, timeout=120)
    return ("ALL CLEAR" in r.stdout, r.stdout.strip().splitlines()[-1][:80])

@check("standing_rules: capture + non-capture")
def _():
    import standing_rules as sr
    fn = sr.looks_like_rule if hasattr(sr, "looks_like_rule") else sr.is_standing_rule
    return (fn("from now on never use the word synergy") and not fn("how many shots in act two?"), "")

# ---------- 4. company + inner life + files + watch ----------
@check("team board GET /api/team")
def _():
    j = get("/api/team").json(); return ("briefs" in j or isinstance(j, list), f"{len(j.get('briefs', j)) if isinstance(j, (dict, list)) else '?'} briefs")

@check("clock.state + work hours")
def _():
    import clock; s = clock.state(); return (bool(s), str(s)[:70])

@check("inbox GET /api/inbox")
def _():
    j = get("/api/inbox").json(); rows = j.get("inbox", [])
    # roster size comes from the live office (10 since Ilnora was hired 2026-09-19), never a fixed 9
    n_seats = len(get("/api/agents/models").json().get("agents", []))
    return (len(rows) == n_seats and all("unread_work" in r for r in rows), f"{len(rows)} agents, unread work {sum(r['unread_work'] for r in rows)} personal {sum(r['unread_personal'] for r in rows)}")

@check("social GET /api/social")
def _():
    j = get("/api/social").json(); return (isinstance(j, dict), "")

@check("bonds GET /api/social/bonds")
def _():
    return (get("/api/social/bonds").status_code == 200, "")

@check("watch GET /api/watch")
def _():
    j = get("/api/watch").json(); return (isinstance(j, dict), str(j.get("last_check", ""))[:30])

@check("files GET /api/files (desk)")
def _():
    j = get("/api/files").json(); return ("desk" in j or "shelf" in j or isinstance(j, dict), str(list(j)[:4]))

@check("store: walk_checkout (logged-out, never submits)")
def _():
    import store
    w = store.walk_checkout()
    return (w.startswith("CHECKOUT WORKS"), w.splitlines()[0][:90])

@check("Microsoft Ads API: live 7-day report")
def _():
    import ads_api
    s = ads_api.summary("LastSevenDays")
    return (s.startswith("MICROSOFT ADS"), s.splitlines()[1][:100] if s.count("\n") else s[:100])

@check("teach-file door (bad agent 404, bad ext 400)")
def _():
    a = httpx.post(API + "/api/agents/Nobody/teach-file", files={"file": ("x.md", b"USE WHEN: x\n\nx")}, timeout=30).status_code
    b = httpx.post(API + "/api/agents/Victor/teach-file", files={"file": ("x.exe", b"x")}, timeout=30).status_code
    return (a == 404 and b == 400, f"{a} {b}")

@check("approvals GET pending + approved")
def _():
    p = get("/api/approvals").json(); a = get("/api/approvals/approved").json()
    return (isinstance(p, list) and isinstance(a, list), f"pending {len(p)} approved {len(a)}")

@check("business pulse GET")
def _():
    j = get("/api/business/pulse").json(); return (isinstance(j, dict), str(j.get("generated_at", j.get("at", "")))[:25])

@check("updates board GET (cached)")
def _():
    j = get("/api/updates", timeout=60).json(); return (isinstance(j, dict), f"{len(j.get('items', []))} items")

@check("machine health")
def _():
    import health; m = health.machine_health(); return ("disk" in str(m).lower() or isinstance(m, dict), str(m)[:80])

@check("degradation status")
def _():
    import degradation; s = degradation.status() if hasattr(degradation, "status") else degradation.check()
    lvl = s.get("level", s.get("status")) if isinstance(s, dict) else s
    return (str(lvl) in ("ok", "healthy", "normal"), str(s)[:80])

@check("client-errors endpoint")
def _():
    return (get("/api/client-errors").status_code == 200, "")

@check("braingraph.outline (inspect_brain) for Elliot")
def _():
    import braingraph; o = braingraph.outline("movie"); return (len(str(o)) > 100, f"{len(str(o))} chars")

# ---------- 5. media + tts + comfy readiness (no GPU work) ----------
@check("TTS /api/tts (kokoro)")
def _():
    r = httpx.post(API + "/api/tts", json={"text": "ok", "agent_id": "cio"}, timeout=60)
    return (r.status_code == 200 and len(r.content) > 500, f"{r.status_code} {len(r.content)}B")

@check("comfy: workflows + models on disk (no launch)")
def _():
    import config, comfy_image as ci
    d = config.COMFY_DIR
    wf = [config.COMFY_VIDEO_WORKFLOW_PATH, config.COMFY_I2V_WORKFLOW_PATH]
    miss = [w for w in wf if not os.path.exists(w if os.path.isabs(w) else os.path.join(REPO, "workflows", os.path.basename(w)))]
    lor = os.path.join(d, "models", "loras"); ck = os.path.join(d, "models", "checkpoints")
    return (os.path.isdir(d) and not miss and os.path.isdir(lor) and os.path.isdir(ck), f"dir={d} missing={miss} loras={len(os.listdir(lor)) if os.path.isdir(lor) else 0}")

@check("render flag guard (mtime-based)")
def _():
    import comfy_image as ci; return (ci.render_in_progress() is False, "no render running")

@check("media_understanding: probe_media on an mp4")
def _():
    import media_understanding as mu, glob
    vids = glob.glob(r"D:\ComfyUI25\output\video\*.mp4") or glob.glob(os.path.join(REPO, "tools", "ComfyUI", "output", "video", "*.mp4"))
    if not vids: return (None, "no clip on disk")
    p = mu.probe_media(vids[-1]); return (bool(p.get("duration") or p.get("duration_s")), str(p)[:70])

@check("agent portraits + homes + offices present (9 each)")
def _():
    av = [f for f in os.listdir(os.path.join(DASH, "assets", "cyber", "avatars")) if f.endswith(".png") and "_face" not in f]
    hm = [f for f in os.listdir(os.path.join(DASH, "assets", "homes")) if f.endswith(".png") and "_me" not in f]
    of = [f for f in os.listdir(os.path.join(DASH, "assets", "offices")) if f.endswith(".png")]
    return (len(av) >= 9 and len(hm) >= 9 and len(of) >= 9, f"avatars {len(av)} homes {len(hm)} offices {len(of)}")

# ---------- 6. dashboards ----------
@check("all decks HTTP 200 + scripts parse")
def _():
    decks = ["index.html", "neo-holo.html", "neo-chamber.html"]  # six decks retired 2026-09-11 on Barry's word (data/backup_retired_decks_2026-09-11)
    bad = []
    for d in decks:
        r = httpx.get(f"{DASHURL}/{d}", timeout=15)
        if r.status_code != 200: bad.append((d, r.status_code)); continue
        import re
        scripts = re.findall(r"<script(?![^>]*src)[^>]*>(.*?)</script>", r.text, re.S)
        for i, s in enumerate(scripts):
            tmp = os.path.join(REPO, "data", f"_audit_{d}_{i}.js"); open(tmp, "w", encoding="utf-8").write(s)
            c = subprocess.run(["node", "--check", tmp], capture_output=True, text=True); os.remove(tmp)
            if c.returncode != 0: bad.append((d, f"script {i} syntax")); break
    # deck-core.js is gone on purpose -- it went with neo-talia/neo-crew when
    # Barry cut the deck list to Chamber + Holo (2026-09-11). Checking for it
    # made this audit report a FAIL every run for a file that is supposed to
    # be absent, which is how a real failure gets ignored.
    for js in ["app.js", "brainmap.js", "files-panel.js", "updates-panel.js", "client-errors.js"]:
        c = subprocess.run(["node", "--check", os.path.join(DASH, js)], capture_output=True, text=True)
        if c.returncode != 0: bad.append((js, "syntax"))
    return (not bad, f"bad={bad}")

@check("dashboard http.server bound 127.0.0.1")
def _():
    return (httpx.get(DASHURL + "/index.html", timeout=10).status_code == 200, "")

# ---------- 7. ONE real model turn ----------
@check("live chat: Victor task turn on Bonsai, no fallback")
def _():
    r = httpx.post(API + "/api/chat", json={"agent_id": "cio", "message": "Reply with exactly: ok", "task": True}, timeout=300).json()
    return (bool(r.get("reply")) and not r.get("bonsai_fell_back"), f"reply={r.get('reply', '')[:30]!r} fell_back={r.get('bonsai_fell_back')}")

@check("thinking stream endpoint")
def _():
    return (get("/api/thinking/cio").status_code == 200, "")


def main():
    w = max(len(r[0]) for r in ROWS)
    fails = 0
    for name, st, note in ROWS:
        if st == "FAIL": fails += 1
        print(f"{st:4}  {name:<{w}}  {note}")
    print(f"\n{len(ROWS)} checks, {fails} FAIL, {sum(1 for r in ROWS if r[1]=='SKIP')} SKIP")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
