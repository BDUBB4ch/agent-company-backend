"""Bonsai 2 + compressed KV cache on Barry's real desktop -- 2026-09-24.

Bonsai 2 was reverted 09-21 because at 98304 with an f16 KV cache it needed 14.1 GB and spilled on his
desktop (15.6 tok/s). The q8_0 KV cache that fixed Bonsai 1 (09-22) was never tried on Bonsai 2.
Configs (all Bonsai 2, HIP build, ctx 98304, launched like bonsai_llm.py on 8811):
  see CONFIGS below.
Per config: load, VRAM dedicated/shared, generation speed on a short ask, and a ~70K-token
long-context check with a planted fact (retrieval = the quality signal KV compression can hurt).
Owns data/video_rendering.flag for the whole run (office LLM calls stand down, nothing reloads
Bonsai 1 mid-test). No office chat turns (no test lines in any agent thread).
Restores production at the end: kill 8811, clear OUR flag; the office relaunches Bonsai 1 on its next call.
"""
import json, os, re, subprocess, sys, time
import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B2 = os.path.join(ROOT, "models", "bonsai2")
EXE = os.path.join(ROOT, "tools", "llama-prism", "hip", "llama-server.exe")
MODEL = os.path.join(B2, "Ternary-Bonsai-2-27B-Abliterated-PQ2_0.gguf")
MMPROJ = os.path.join(B2, "Ternary-Bonsai-2-27B-mmproj-BF16.gguf")
FLAG = os.path.join(ROOT, "data", "video_rendering.flag")
TOKEN = f"bench-bonsai2-kv-{time.time()}"
OUT = os.path.join(ROOT, "data", "bench_bonsai2_kv_2026-09-24.json")
CTX = 98304
NEEDLE = "The warehouse door code for the Colorado Springs unit is 7-4-1-9-Delta."

# PrismML fork's own K-cache mean-centering (tools/llama-prism/*/llama-kv-mean-center.exe): a per-layer
# bias subtracted from K before q4_0 quantisation. Calibration text = business material only (no chats).
KVMC_EXE = os.path.join(ROOT, "tools", "llama-prism", "hip", "llama-kv-mean-center.exe")
KVMC = os.path.join(ROOT, "data", "kvmc", "bonsai2-kv-mean-center.gguf")
CALIB = os.path.join(ROOT, "data", "kvmc", "calibration.txt")

# label, KV types (K, V), extra args
CONFIGS = [
    ("A_f16", ("f16", "f16"), []),
    ("B_q8", ("q8_0", "q8_0"), []),
    ("C_q8_mmproj_cpu", ("q8_0", "q8_0"), ["--no-mmproj-offload"]),
    ("D_k4mc_v8_mmproj_cpu", ("q4_0", "q8_0"), ["--no-mmproj-offload", "--kv-mean-center", KVMC]),
    ("E_k4mc_v4_mmproj_cpu", ("q4_0", "q4_0"), ["--no-mmproj-offload", "--kv-mean-center", KVMC]),
]
if os.getenv("BENCH_ONLY"):
    CONFIGS = [c for c in CONFIGS if c[0] in os.getenv("BENCH_ONLY").split(",")]


def gpu_mem():
    ps = ("$d=((Get-Counter '\\GPU Adapter Memory(*)\\Dedicated Usage').CounterSamples | Measure-Object CookedValue -Maximum).Maximum;"
          "$s=((Get-Counter '\\GPU Adapter Memory(*)\\Shared Usage').CounterSamples | Measure-Object CookedValue -Maximum).Maximum;"
          "'{0} {1}' -f $d,$s")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout.split()
    return {"dedicated_MB": round(float(out[0]) / 2**20), "shared_MB": round(float(out[1]) / 2**20)}


def kill_8811():
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-NetTCPConnection -LocalPort 8811 -State Listen -ErrorAction SilentlyContinue | "
                    "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"], capture_output=True)
    time.sleep(5)


def launch(kv, extra, log):
    kill_8811()
    args = [EXE, "-m", MODEL, "--host", "127.0.0.1", "--port", "8811", "--jinja", "-ngl", "99",
            "-c", str(CTX), "-np", "1", "--kv-unified", "--reasoning-budget", "-1", "--mmproj", MMPROJ]
    if kv != ("f16", "f16"):
        args += ["-fa", "on", "-ctk", kv[0], "-ctv", kv[1]]
    args += extra
    fh = open(log, "w", encoding="utf-8", errors="replace")
    p = subprocess.Popen(args, stdout=fh, stderr=subprocess.STDOUT,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(240):
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
    return {"prefill": pe[-2:], "generate": ev[-2:]}


def chat(messages, max_tokens):
    t = time.time()
    r = httpx.post("http://127.0.0.1:8811/v1/chat/completions",
                   json={"messages": messages, "max_tokens": max_tokens, "cache_prompt": False,
                         "thinking_budget_tokens": 1024}, timeout=2400)
    j = r.json()
    msg = (j.get("choices") or [{}])[0].get("message", {})
    return {"status": r.status_code, "seconds": round(time.time() - t, 1),
            "prompt_tokens": (j.get("usage") or {}).get("prompt_tokens"),
            "answer": (msg.get("content") or "")[:500], "error": str(j.get("error"))[:300] if j.get("error") else None}


def long_ctx():
    d = json.load(open(os.path.join(ROOT, "data", "bonsai_prompt_cache", "movie.json"), encoding="utf-8"))
    filler = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8", errors="replace").read()
    body = (filler * 4)[:120000]
    cut = int(len(body) * 0.35)  # needle deep in the middle -- where compression hurts most
    body = body[:cut] + "\n" + NEEDLE + "\n" + body[cut:]
    msgs = [{"role": "system", "content": d["system_prompt"]},
            {"role": "user", "content": "Reference material follows.\n\n" + body
             + "\n\nWhat is the warehouse door code for the Colorado Springs unit? Answer with the code only."}]
    return chat(msgs, 2000)


results = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "ctx": CTX}
try:
    if os.path.exists(FLAG) and os.path.getsize(FLAG) > 0 and time.time() - os.path.getmtime(FLAG) < 7200:
        raise SystemExit("a render holds the GPU flag -- not starting")
    open(FLAG, "w").write(TOKEN)
    results["vram_before_MB"] = gpu_mem()
    if any("--kv-mean-center" in c[2] for c in CONFIGS) and not os.path.exists(KVMC):
        kill_8811()
        t = time.time()
        p = subprocess.run([KVMC_EXE, "-m", MODEL, "-f", CALIB, "-o", KVMC, "-c", "512", "--chunks", "64", "-ngl", "99"],
                           capture_output=True, text=True, timeout=1800,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        results["kvmc_build"] = {"seconds": round(time.time() - t), "ok": os.path.exists(KVMC),
                                 "tail": (p.stdout + p.stderr)[-600:]}
        print("kv-mean-center:", results["kvmc_build"]["ok"], results["kvmc_build"]["seconds"], "s", flush=True)
    for label, kv, extra in CONFIGS:
        if "--kv-mean-center" in extra and not os.path.exists(KVMC):
            results[label] = {"skipped": "no mean-center file"}
            continue
        log = os.path.join(ROOT, "data", f"b2kv_{label}.log")
        print(f"== {label}", flush=True)
        res = {"kv": kv, "extra": extra}
        try:
            launch(kv, extra, log)
            time.sleep(8)
            res["vram_loaded"] = gpu_mem()
            mark = os.path.getsize(log)
            res["short"] = chat([{"role": "user", "content": "Name three things a grow tent fan does, one line each."}], 1500)
            res["short_timing"] = timings(log, mark)
            mark = os.path.getsize(log)
            res["long"] = long_ctx()
            res["long_found_needle"] = "7-4-1-9" in (res["long"]["answer"] or "").replace(" ", "")
            res["vram_after_long"] = gpu_mem()
            res["long_timing"] = timings(log, mark)
        except Exception as e:
            res["error"] = f"{type(e).__name__}: {e}"[:400]
        results[label] = res
        print(json.dumps(res, indent=1)[:2000], flush=True)
        json.dump(results, open(OUT, "w", encoding="utf-8"), indent=1)
finally:
    kill_8811()
    try:
        if open(FLAG).read().strip() == TOKEN:
            os.remove(FLAG)
    except OSError:
        pass
    print("test server stopped, flag cleared; results in", OUT, flush=True)
