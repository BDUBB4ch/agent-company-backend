"""Can the agents live on CPU so they never fight the GPU?

Barry, 2026-08-29: "they can stay live on cpu and i can chat allday and they
could generate images without interuptions."

THE PRIZE: today ONE thing owns the 16GB card at a time. A render blocks every
chat; a chat evicts the render. If conversation ran on CPU instead, both could
happen at once -- he talks all day while images generate.

THE COST, and this is what the test measures: LLM inference is MEMORY-BANDWIDTH
bound, not core bound. Every token reads the whole model out of RAM. His 24
cores will mostly sit waiting on ~100 GB/s system memory where the GPU has
600+. So the question is not "does it work" -- it does -- but "is it fast
enough to be worth having".

Read-only, CPU-only (num_gpu=0), safe to run WHILE a render is going -- which
is itself the first proof of the idea.
"""
import json
import sys
import time
import urllib.request

OLLAMA = "http://127.0.0.1:11434"
PROMPT = ("You are at home, off the clock, talking to a coworker who just "
          "asked how your day went. Answer in three or four natural "
          "sentences, in your own voice.")


def run(model, num_gpu, label, num_predict=120):
    body = {
        "model": model,
        "prompt": PROMPT,
        "stream": False,
        "options": {"num_gpu": num_gpu, "num_predict": num_predict,
                    "temperature": 0.8},
    }
    req = urllib.request.Request(
        f"{OLLAMA}/api/generate", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=1800).read())
    except Exception as e:
        print(f"  {label:22s} FAILED: {str(e)[:70]}")
        return None
    wall = time.time() - t0
    out_tok = r.get("eval_count") or 0
    tps = out_tok / (r.get("eval_duration", 1) / 1e9) if r.get("eval_duration") else 0
    print(f"  {label:22s} {wall:6.1f}s wall | {out_tok:4d} tokens | "
          f"{tps:5.1f} tok/s")
    print(f"    -> {(r.get('response') or '').strip()[:150]}")
    return {"label": label, "wall_s": round(wall, 1), "tokens": out_tok,
            "tok_per_s": round(tps, 1)}


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "huihui_ai/qwen3.5-abliterated:9b"
    print(f"model: {model}")
    print("(a render may be using the GPU right now -- the CPU run should not "
          "care, and that is the whole point)\n")
    results = []
    for num_gpu, label in ((0, "CPU only"),):
        res = run(model, num_gpu, label)
        if res:
            results.append(res)
    print()
    if results:
        t = results[0]["tok_per_s"]
        print(f"VERDICT at {t:.1f} tok/s on CPU:")
        print(f"  a 120-token reply  ~ {120/t:5.0f}s")
        print(f"  a 300-token reply  ~ {300/t:5.0f}s")
        print("  (Bonsai on the GPU does ~40 tok/s = 3s and 8s)")
        print()
        if t >= 8:
            print("  USABLE for background chatter, and borderline for live "
                  "chat if he is patient.")
        elif t >= 3:
            print("  Fine for BACKGROUND life (nobody waits on a 2am break "
                  "room talk). Too slow to talk to directly.")
        else:
            print("  Too slow even for background -- a group chat would take "
                  "many minutes per turn.")
    json.dump(results, open("data/cpu_inference_test.json", "w"), indent=1)


if __name__ == "__main__":
    main()
