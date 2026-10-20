"""Bonsai 1 + compressed KV cache (q8_0) for Elliot -- Barry, 2026-09-22.

Question: can Bonsai 1 hold a bigger window for Elliot WITHOUT spilling, if the
KV cache is stored at q8_0 instead of f16? Bonsai 1 at 98304/f16 measured
3.7 tok/s on 2026-09-11 (spill). Two configs, same card state:
  A  f16  @ 49152   (today's production)
  B  q8_0 @ 98304   (candidate)
For each: launch the server on 8811 exactly like bonsai_llm.py does (+ the KV
flags), then (1) one real Elliot task turn through the office's /api/chat, and
(2) one direct oversized prompt (~70K tokens, B only) to prove the window is real.
Reads VRAM dedicated/shared and the server's own timing lines. Restores
production at the end by killing the test server (the office relaunches its own).
"""
import json, os, re, subprocess, sys, time
import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import config  # noqa: E402

EXE, MODEL, MMPROJ = config.BONSAI_SERVER_EXE, config.BONSAI_MODEL_PATH, config.BONSAI_MMPROJ_PATH
OUT = os.path.join(ROOT, "data", "bench_bonsai1_kvquant_2026-09-22.json")
ASK = "Give me the Seedance prompt for SHOT 03."


def gpu_mem():
    ps = ("$d=((Get-Counter '\\GPU Adapter Memory(*)\\Dedicated Usage').CounterSamples | Measure-Object CookedValue -Maximum).Maximum;"
          "$s=((Get-Counter '\\GPU Adapter Memory(*)\\Shared Usage').CounterSamples | Measure-Object CookedValue -Maximum).Maximum;"
          "'{0} {1}' -f $d,$s")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout.split()
    return round(float(out[0]) / 2**20), round(float(out[1]) / 2**20)


def kill_8811():
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-NetTCPConnection -LocalPort 8811 -State Listen -ErrorAction SilentlyContinue | "
                    "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"], capture_output=True)
    time.sleep(4)


def launch(kv, ctx, log):
    kill_8811()
    args = [EXE, "-m", MODEL, "--host", "127.0.0.1", "--port", "8811", "--jinja", "-ngl", "99",
            "-c", str(ctx), "-np", "1", "--kv-unified", "--reasoning-budget", "-1", "--mmproj", MMPROJ]
    if kv != "f16":
        args += ["-fa", "on", "-ctk", kv, "-ctv", kv]
    fh = open(log, "w", encoding="utf-8", errors="replace")
    p = subprocess.Popen(args, stdout=fh, stderr=subprocess.STDOUT,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(180):
        try:
            if httpx.get("http://127.0.0.1:8811/health", timeout=3).status_code == 200:
                return p
        except Exception:
            pass
        if p.poll() is not None:
            raise RuntimeError(f"server exited early, see {log}")
        time.sleep(2)
    raise RuntimeError("server never became healthy")


def timings(log, since):
    txt = open(log, encoding="utf-8", errors="replace").read()[since:]
    pe = re.findall(r"prompt eval time =\s*([\d.]+) ms /\s*(\d+) tokens.*?([\d.]+) tokens per second", txt)
    ev = re.findall(r"\beval time =\s*([\d.]+) ms /\s*(\d+) tokens.*?([\d.]+) tokens per second", txt)
    return {"prefill": pe[-3:], "generate": ev[-3:], "n_ctx": re.findall(r"n_ctx(?:_slot)?\s*=\s*(\d+)", txt)[:3]}


def office_turn():
    t = time.time()
    r = httpx.post("http://127.0.0.1:8420/api/chat",
                   json={"agent_id": "movie", "message": ASK, "task": True}, timeout=1200).json()
    rep = r.get("reply") or ""
    return {"seconds": round(time.time() - t, 1), "fell_back": r.get("bonsai_fell_back"),
            "chars": len(rep), "has_fence": "```" in rep, "head": rep[:300]}


def big_prompt():
    d = json.load(open(os.path.join(ROOT, "data", "bonsai_prompt_cache", "movie.json"), encoding="utf-8"))
    filler = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8", errors="replace").read()
    msgs = [{"role": "system", "content": d["system_prompt"]},
            {"role": "user", "content": "Reference material follows.\n\n" + (filler * 3)[:115000]
             + "\n\nIn two sentences: what is this episode about?"}]
    t = time.time()
    r = httpx.post("http://127.0.0.1:8811/v1/chat/completions",
                   json={"messages": msgs, "max_tokens": 1500, "cache_prompt": False}, timeout=1800)
    j = r.json()
    msg = (j.get("choices") or [{}])[0].get("message", {})
    return {"status": r.status_code, "seconds": round(time.time() - t, 1),
            "prompt_tokens": (j.get("usage") or {}).get("prompt_tokens"),
            "answer": (msg.get("content") or "")[:400], "error": str(j.get("error"))[:300] if j.get("error") else None}


results = {}
try:
    for label, kv, ctx, big in [("A_f16_49152", "f16", 49152, False), ("B_q8_98304", "q8_0", 98304, True)]:
        log = os.path.join(ROOT, "data", f"kvq_{label}.log")
        print(f"== {label}", flush=True)
        launch(kv, ctx, log)
        res = {"vram_loaded_MB(ded,shared)": gpu_mem()}
        mark = os.path.getsize(log)
        res["elliot_turn"] = office_turn()
        res["vram_after_turn"] = gpu_mem()
        res["elliot_timing"] = timings(log, mark)
        if big:
            mark = os.path.getsize(log)
            res["oversized"] = big_prompt()
            res["vram_after_big"] = gpu_mem()
            res["big_timing"] = timings(log, mark)
        results[label] = res
        print(json.dumps(res, indent=1)[:2500], flush=True)
        json.dump(results, open(OUT, "w", encoding="utf-8"), indent=1)
finally:
    kill_8811()   # production server relaunches on the office's next Bonsai call
    print("test server stopped; results in", OUT)
