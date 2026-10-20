"""Model bake-off for Ilnora's video turns (2026-10-07, Barry: "yes download both and test them" / "test the fastest
way possible, with accuracy"). Through the SHIPPED path: the real backend, her real prompt/tools/checks/fix rounds;
only the model behind bonsai_llm changes (temporary .env override, restored at the end).
Per model: her intro Short + the epic Long, ONE make_one run each (with its own fix rounds), Barry's words verbatim.
Measured: valid video (passed every office check), minutes, loop cuts, fallbacks, tok/s, the video itself.
Videos that pass are kept for Barry in data/video_queue/model_test/<model>/ (never built automatically).
Results: data/video_queue/model_test/results.json + .md"""
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))
import comfy_image  # noqa: E402
import video_queue as Q  # noqa: E402

ENV = os.path.join(ROOT, ".env")
ENV_BAK = os.path.join(ROOT, "data", "env_backup_before_bakeoff_2026-10-07")
OUT = os.path.join(ROOT, "data", "video_queue", "model_test")
EVENTS = os.path.join(ROOT, "data", "bonsai_events.log")
SRV = os.path.join(ROOT, "data", "bonsai_server.log")
CAND = os.path.join(ROOT, "models", "candidates")
MODELS = [
    ("qwen38-27b-iq3m", os.path.join(CAND, "Huihui-Qwen3.8-27B-abliterated.i1-IQ3_M.gguf"), 40960),
    ("cydonia-24b-iq4xs", os.path.join(CAND, "TheDrummer_Cydonia-24B-v4.3-IQ4_XS.gguf"), 32768),
]
FULL = ('FROM BARRY (his whole message, his words): "I like the videos. One thing i want to correct. I do want her to '
        'show the text for the plants she is talking about on the screen for a couple of seconds. thats it. Ok, i '
        'want 2 more vids. the first is a short of her introducing herself. and the second. lets do a longform. new '
        'plant or plants, something epic and cool as fuck!"')
ASKS = [("short", FULL + " -- THIS video is the first one: the Short of you introducing yourself."),
        ("long", FULL + " -- THIS video is the second one: the Long.")]


def log(m: str) -> None:
    os.makedirs(OUT, exist_ok=True)
    line = f"{time.strftime('%H:%M:%S')} {m}"
    print(line, flush=True)
    open(os.path.join(OUT, "bakeoff.log"), "a", encoding="utf-8").write(line + "\n")


def ps(cmd: str) -> None:
    subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True)


def set_env(model_path: str | None, ctx: int | None) -> None:
    lines = open(ENV_BAK, encoding="utf-8").read().splitlines()
    lines = [l for l in lines if not re.match(r"^(BONSAI_MODEL_PATH|BONSAI_MMPROJ_PATH|BONSAI_NUM_CTX)=", l)]
    if model_path:
        lines += [f"BONSAI_MODEL_PATH={model_path}", f"BONSAI_MMPROJ_PATH={model_path}.no-vision",
                  f"BONSAI_NUM_CTX={ctx}"]
    open(ENV, "w", encoding="utf-8").write("\n".join(lines) + "\n")


async def restart() -> None:
    n0 = open(Q.LOG, encoding="utf-8").read().count("loop started")
    ps("Get-NetTCPConnection -LocalPort 8811 -State Listen -ErrorAction SilentlyContinue | "
       "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }")
    ps("$procId=(Get-NetTCPConnection -LocalPort 8420 -State Listen).OwningProcess; Stop-Process -Id $procId -Force")
    for _ in range(150):
        await asyncio.sleep(5)
        if open(Q.LOG, encoding="utf-8").read().count("loop started") > n0:
            break
    await asyncio.sleep(30)


def count(path: str, pat: str, since: str) -> int:
    try:
        return sum(1 for l in open(path, encoding="utf-8", errors="replace") if l[:19] >= since and re.search(pat, l))
    except OSError:
        return 0


def server_stats(since_bytes: int) -> dict:
    t = open(SRV, encoding="utf-8", errors="replace").read()[since_bytes:]
    gen = [float(x) for x in re.findall(r"eval time = .*?\(.*?([\d.]+) tokens per second\)", t)]
    loaded = re.findall(r"(llama_model_load|load_tensors|CUDA|ROCm0 model buffer size = +[\d.]+ MiB|KV self size.*|"
                        r"llama_context: +ROCm0 compute buffer size = +[\d.]+ MiB)", t)
    return {"gen_tok_s_median": sorted(gen)[len(gen) // 2] if gen else None, "gen_samples": len(gen),
            "load_lines": [l for l in loaded if "MiB" in l][:6]}


async def run_model(name: str, path: str, ctx: int) -> dict:
    log(f"=== {name} (ctx {ctx})")
    set_env(path, ctx)
    srv0 = os.path.getsize(SRV) if os.path.isfile(SRV) else 0
    await restart()
    res = {"model": name, "ctx": ctx, "asks": []}
    os.makedirs(os.path.join(OUT, name), exist_ok=True)
    for form, words in ASKS:
        since = time.strftime("%Y-%m-%d %H:%M:%S")
        before = {j["_file"] for j in Q._jobs()}
        open(comfy_image._REEL_MARK, "w").write(f"model test {name}")
        t0 = time.time()
        try:
            ok = await Q.make_one(form, f"model test {name}", words, use_plan=False)
        except Exception as exc:  # noqa: BLE001
            ok = False
            log(f"{name} {form}: crashed {type(exc).__name__}: {exc}")
        finally:
            try:
                os.remove(comfy_image._REEL_MARK)
            except OSError:
                pass
        mins = round((time.time() - t0) / 60, 1)
        got = None
        for j in Q._jobs():
            if j["_file"] not in before:
                p = j["pkg"]
                sc = p.get("scenes") or []
                got = {"title": p.get("title"), "words": sum(len(s.get("narration", "").split()) for s in sc),
                       "parts": len(sc), "plants": sorted({s.get("plant") for s in sc if s.get("plant")}),
                       "first_line": (sc[0].get("narration", "") if sc else "")[:300]}
                shutil.move(j["_file"], os.path.join(OUT, name, os.path.basename(j["_file"])))
        a = {"form": form, "valid_video": bool(ok and got), "minutes": mins, "video": got,
             "loop_cuts": count(EVENTS, r"LOOP STOP ilnora", since),
             "cut_short": count(EVENTS, r"FINAL CUT SHORT ilnora|max_tokens", since),
             "fallbacks": count(EVENTS, r"SLOW REQUEST ilnora|call_ollama|EMPTY REPLY ilnora", since)}
        log(f"{name} {form}: {json.dumps(a, ensure_ascii=False)[:400]}")
        res["asks"].append(a)
    res["server"] = server_stats(srv0)
    return res


async def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    if not os.path.isfile(ENV_BAK):
        shutil.copy2(ENV, ENV_BAK)
    results = []
    try:
        for name, path, ctx in MODELS:
            if not os.path.isfile(path):
                log(f"{name}: file missing -- skipped")
                continue
            results.append(await run_model(name, path, ctx))
            json.dump(results, open(os.path.join(OUT, "results.json"), "w", encoding="utf-8"), indent=1,
                      ensure_ascii=False)
    finally:
        shutil.copy2(ENV_BAK, ENV)                     # Bonsai back, always
        log("restoring Bonsai")
        await restart()
    md = ["# Ilnora model bake-off 2026-10-07", ""]
    for r in results:
        md.append(f"## {r['model']} (ctx {r['ctx']}) -- gen {r['server'].get('gen_tok_s_median')} tok/s")
        for a in r["asks"]:
            v = a["video"] or {}
            md.append(f"- {a['form']}: valid={a['valid_video']} in {a['minutes']} min | loops {a['loop_cuts']} | "
                      f"cut-short {a['cut_short']} | fallbacks {a['fallbacks']} | {v.get('title')} | "
                      f"{v.get('words')} words | plants {v.get('plants')}")
            if v.get("first_line"):
                md.append(f"  - opens: {v['first_line']}")
    open(os.path.join(OUT, "results.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    log("done")


if __name__ == "__main__":
    asyncio.run(main())
