"""Get a REAL LTX baseline. Same settings, repeated, with conditions recorded.

Why: the "7 min per 5s clip" in CLAUDE.md is not reliable. Real durations pulled
from comfyui.log across five past runs were 4.4 / 7.8 / 14.6 / 20.5 / 27.5 min --
a 6x spread with no recorded settings, so there is nothing to compare against.
Without a baseline the MXFP8 experiment is meaningless: we could not tell a real
speedup from catching a warm run.

Leading hypothesis this is designed to test: it is COLD vs WARM model loading.
The pipeline holds ltx-2.3-22b-dev-fp8 (29GB) plus a 12B text encoder plus a
spatial upscaler on a 16GB card, so anything that touches the GPU in between
evicts them and forces a reload from disk. Run 1 pays that; run 2 should not.

Usage:
    python scripts/time_ltx.py --runs 2 --duration 5
"""
import argparse
import json
import time
import urllib.error
import urllib.request

BACKEND = "http://127.0.0.1:8420"
PROMPT = ("a slow push in on a pale grey-white alien woman standing still in a "
          "dim marble atrium, soft light, cinematic")


def run_once(duration_s, label):
    body = {"prompt": PROMPT, "agent_id": "owner", "duration_s": duration_s}
    req = urllib.request.Request(
        f"{BACKEND}/api/generate-video", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=7200).read())
        dt = time.time() - t0
        if "error" in r:
            print(f"  {label}: FAILED after {dt/60:.1f} min -- {r['error'][:200]}")
            return None
        fn = r.get("path", "").replace("\\", "/").split("/")[-1]
        print(f"  {label}: {dt/60:6.2f} min   {fn}")
        return dt
    except urllib.error.HTTPError as e:
        print(f"  {label}: HTTP {e.code} after {(time.time()-t0)/60:.1f} min "
              f"-- {e.read().decode()[:200]}")
    except Exception as e:  # noqa: BLE001
        print(f"  {label}: {type(e).__name__} after {(time.time()-t0)/60:.1f} min -- {e}")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--duration", type=int, default=5)
    a = ap.parse_args()

    print(f"LTX baseline: {a.runs} runs x {a.duration}s clip, identical settings")
    print("Run 1 is COLD (models loading from disk). Later runs should be WARM.\n")
    times = []
    for i in range(1, a.runs + 1):
        t = run_once(a.duration, f"run {i} ({'cold' if i == 1 else 'warm'})")
        if t:
            times.append(t)

    print()
    if len(times) >= 2:
        cold, warm = times[0], min(times[1:])
        print(f"  cold {cold/60:.2f} min -> warm {warm/60:.2f} min "
              f"= {cold/warm:.1f}x difference")
        if cold / warm > 1.5:
            print("  => The spread IS model loading. Keeping the models resident "
                  "between renders is worth more than any quantisation swap.")
        else:
            print("  => Loading is NOT the main cost. A smaller/quantised build "
                  "is the lever worth testing next.")
    elif times:
        print(f"  single successful run: {times[0]/60:.2f} min")
    else:
        print("  no successful runs -- nothing measured")


if __name__ == "__main__":
    main()
