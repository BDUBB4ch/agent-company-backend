"""Can BONSAI 27B itself run on CPU fast enough to talk to?

Barry, 2026-08-29: "im saying if i put their chats even conversations with me
on cpu, 27b will be reverted to 9b?"

Claude's earlier answer assumed yes -- that CPU meant dropping to the 9b. That
assumption may be wrong, which is why this measures instead of guessing.

THE REASON IT MIGHT WORK: CPU inference is memory-bandwidth bound, so speed
tracks the model's SIZE IN BYTES, not its parameter count. Ternary Bonsai is
7.17GB. The 9b is 6.6GB. Nearly identical. A 27B-class brain in the same
memory footprint is the whole point of ternary quantisation.

THE REASON IT MIGHT NOT: ternary kernels may be less optimised on CPU than
standard K-quants, so it could be far slower per byte. Unknown until measured.

Runs a SECOND llama-server on port 8812 with -ngl 0 (zero GPU layers), so it
cannot disturb the live office or the render on the card. Small context to
keep RAM sane. Read-only, safe to run mid-render.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
import config  # noqa: E402

PORT = 8812
HOST = f"http://127.0.0.1:{PORT}"
LOG = os.path.join(ROOT, "data", "bonsai_cpu_test.log")
PROMPT = ("You are at home, off the clock, and a coworker just asked how your "
          "day went. Answer in three or four natural sentences.")


def wait_up(proc, timeout=600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc.poll() is not None:
            return False
        try:
            urllib.request.urlopen(f"{HOST}/health", timeout=3).read()
            return True
        except Exception:
            time.sleep(3)
    return False


def main():
    args = [
        config.BONSAI_SERVER_EXE,
        "-m", config.BONSAI_MODEL_PATH,
        "--host", "127.0.0.1", "--port", str(PORT),
        "-ngl", "0",              # ZERO layers on GPU -- pure CPU
        "-c", "4096",             # small ctx: this is a speed probe
        "-t", "20",               # leave a few cores for the render
        "--no-warmup",
        "-np", "1",
    ]
    print("starting a SEPARATE llama-server on CPU only (port 8812)...")
    print("this does not touch the live office on 8811 or the GPU\n")
    log = open(LOG, "a", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT)
    try:
        t0 = time.time()
        if not wait_up(proc):
            print("server did not come up -- see data/bonsai_cpu_test.log")
            return
        print(f"loaded in {time.time()-t0:.0f}s (CPU load reads the whole "
              "7.2GB from disk/RAM)\n")

        body = {"messages": [{"role": "user", "content": PROMPT}],
                "max_tokens": 200, "temperature": 0.8, "stream": False}
        req = urllib.request.Request(
            f"{HOST}/v1/chat/completions", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"})
        t0 = time.time()
        r = json.loads(urllib.request.urlopen(req, timeout=1800).read())
        wall = time.time() - t0
        txt = (r["choices"][0]["message"].get("content") or "").strip()
        usage = r.get("usage", {})
        out = usage.get("completion_tokens", 0)
        tps = out / wall if wall else 0
        print(f"BONSAI 27B ON CPU: {wall:.1f}s wall | {out} tokens | "
              f"{tps:.1f} tok/s")
        print(f"reply: {txt[:220]}\n")
        print("for comparison:")
        print("  Bonsai on the GPU   ~40.0 tok/s")
        print("  the 9b on CPU        ~9.4 tok/s (measured tonight)")
        print()
        if tps >= 6:
            print("VERDICT: the 27B runs on CPU at usable speed. Chat could "
                  "move off the GPU WITHOUT dropping to the 9b.")
        elif tps >= 2:
            print("VERDICT: usable for BACKGROUND life only. Too slow to talk "
                  "to directly -- a normal reply would take minutes.")
        else:
            print("VERDICT: too slow. CPU chat would mean the 9b after all.")
        json.dump({"tok_per_s": round(tps, 2), "wall_s": round(wall, 1),
                   "tokens": out},
                  open(os.path.join(ROOT, "data",
                                    "bonsai_cpu_test.json"), "w"), indent=1)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except Exception:
            proc.kill()
        print("\ntest server stopped; the live office is untouched.")


if __name__ == "__main__":
    main()
