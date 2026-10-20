"""Bonsai 2 speed on the NEW AMD driver (2026-10-09, Barry: "run the bench" after updating the card).
Same method as the 10-02 A/B (bonsai_laya_ab_2026_10_02.py): fresh Bonsai via a backend restart (boot prewarm
starts it -- the shipped path), VRAM split, then a fixed direct /completion, 300 tokens, no prompt cache.
Baseline on the old driver (10-02, Laya on CPU): 47.8 tok/s, llama-server 10.72 GB dedicated / 0.24 GB shared.
-> data/bench_bonsai2_driver_2026_10_09.json"""
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import bonsai_laya_ab_2026_10_02 as AB  # noqa: E402

OUT = os.path.join(ROOT, "data", "bench_bonsai2_driver_2026_10_09.json")
FLAG = os.path.join(ROOT, "data", "video_rendering.flag")


def main() -> None:
    if os.path.exists(FLAG) or os.path.exists(os.path.join(ROOT, "data", "reel_building.flag")):
        raise SystemExit("a render/build owns the card -- not benching")
    driver = subprocess.run(["powershell", "-NoProfile", "-Command",
                             "(Get-CimInstance Win32_VideoController | Select-Object -First 1).DriverVersion"],
                            capture_output=True, text=True).stdout.strip()
    t0 = time.time()
    AB.fresh_bonsai()
    boot_s = round(time.time() - t0)
    res = {"driver": driver, "when": time.strftime("%Y-%m-%d %H:%M"), "bonsai_boot_s": boot_s,
           "vram_after_boot": AB.vram(), "runs_tok_s": [], "baseline_old_driver_tok_s": 47.8}
    print("driver", driver, "boot", boot_s, "s", res["vram_after_boot"], flush=True)
    for _ in range(3):
        s = AB.speed()
        res["runs_tok_s"].append(s)
        print("tok/s", s, flush=True)
    res["tok_s_median"] = sorted(res["runs_tok_s"])[1]
    res["vram_after_runs"] = AB.vram()
    json.dump(res, open(OUT, "w"), indent=1)
    print("saved", OUT, json.dumps({k: res[k] for k in ("tok_s_median", "runs_tok_s", "bonsai_boot_s")}), flush=True)


if __name__ == "__main__":
    main()
