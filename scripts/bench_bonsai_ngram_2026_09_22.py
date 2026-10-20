"""N-gram speculative decoding on Bonsai 1 -- Barry, 2026-09-22 ("go, test the
ngram ... i need all my agents faster").

The PrismML build already ships draft-free speculative decoding (--spec-type
ngram-*): it drafts text the model has already seen (prompt / earlier output)
and the model confirms several tokens per pass. No extra model, ~no VRAM.
Same server config as production (q8_0 KV, 98304), three variants, the same
three REAL asks through the office's own /api/chat (task turns, history-free):
Elliot's shot prompt, Amara (tool + numbers), Victor (plain judgement).
Generation tok/s comes from the server's own timing lines.
"""
import json, os, re, subprocess, sys, time
import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import config  # noqa: E402

OUT = os.path.join(ROOT, "data", "bench_bonsai_ngram_2026-09-22.json")
ASKS = [("movie", "Give me the Seedance prompt for SHOT 04."),
        ("business", "What did the store do in the last 30 days? Revenue, orders and the top seller."),
        ("cio", "In three sentences: what is the single most important thing for the business this month and why?")]
VARIANTS = [("base", []),
            ("ngram-mod", ["--spec-type", "ngram-mod"]),
            ("ngram-simple", ["--spec-type", "ngram-simple"])]


def kill_8811():
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-NetTCPConnection -LocalPort 8811 -State Listen -ErrorAction SilentlyContinue | "
                    "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"], capture_output=True)
    time.sleep(4)


def launch(extra, log):
    kill_8811()
    args = [config.BONSAI_SERVER_EXE, "-m", config.BONSAI_MODEL_PATH, "--host", "127.0.0.1",
            "--port", "8811", "--jinja", "-ngl", "99", "-c", str(config.BONSAI_NUM_CTX), "-np", "1",
            "--kv-unified", "--reasoning-budget", "-1", "--mmproj", config.BONSAI_MMPROJ_PATH,
            "-fa", "on", "-ctk", config.BONSAI_KV_TYPE, "-ctv", config.BONSAI_KV_TYPE] + extra
    fh = open(log, "w", encoding="utf-8", errors="replace")
    p = subprocess.Popen(args, stdout=fh, stderr=subprocess.STDOUT,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(180):
        try:
            if httpx.get("http://127.0.0.1:8811/health", timeout=3).status_code == 200:
                return
        except Exception:
            pass
        if p.poll() is not None:
            raise RuntimeError(f"server exited early, see {log}")
        time.sleep(2)
    raise RuntimeError("server never became healthy")


def gen_rates(log, since):
    txt = open(log, encoding="utf-8", errors="replace").read()[since:]
    ev = re.findall(r"\beval time =\s*([\d.]+) ms /\s*(\d+) tokens", txt)
    acc = re.findall(r"(?i)(draft acceptance rate[^\n]*|accepted[^\n]{0,80})", txt)
    ms = sum(float(a) for a, _ in ev)
    toks = sum(int(b) for _, b in ev)
    return {"gen_tokens": toks, "gen_seconds": round(ms / 1000, 1),
            "gen_tok_s": round(toks / (ms / 1000), 1) if ms else None, "accept_lines": acc[-3:]}


results = {}
try:
    for name, extra in VARIANTS:
        log = os.path.join(ROOT, "data", f"ngram_{name}.log")
        launch(extra, log)
        rows = []
        for agent, ask in ASKS:
            mark = os.path.getsize(log)
            t = time.time()
            r = httpx.post("http://127.0.0.1:8420/api/chat",
                           json={"agent_id": agent, "message": ask, "task": True}, timeout=1500).json()
            rep = r.get("reply") or ""
            row = {"agent": agent, "wall_s": round(time.time() - t, 1),
                   "fell_back": r.get("bonsai_fell_back"), "chars": len(rep),
                   "reply_head": rep[:240], **gen_rates(log, mark)}
            rows.append(row)
            print(name, json.dumps(row)[:400], flush=True)
        results[name] = rows
        json.dump(results, open(OUT, "w", encoding="utf-8"), indent=1)
finally:
    kill_8811()
    print("done ->", OUT)
