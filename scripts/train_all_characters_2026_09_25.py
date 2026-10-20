"""Train every character with a photo-real set, one at a time (Barry 2026-09-25: "train them all and lets be done
for now"). Step 1 is a 10-step probe -- training has never finished on this AMD card and crashed the PC twice at the
model load -- and nothing long runs unless it passes. Each run owns the GPU flag and has the card + RAM guards
(scripts/zimage_lora_2026_09_23.py). Stops at the first failure. Log: data/zimage_lora/train_all.log
Bia and Keth are not here: no photo-real pictures of them yet."""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, "venv", "Scripts", "python.exe")
TRAIN = os.path.join(ROOT, "scripts", "zimage_lora_2026_09_23.py")
LOG = os.path.join(ROOT, "data", "zimage_lora", "train_all.log")
ORDER = ["yannah", "tazz", "bdubb", "vorshara", "ilnora"]
STEPS = 2500


def log(msg):
    line = f"{time.strftime('%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def run(char, *args):
    env = dict(os.environ, ZL_CHAR=char)
    t = time.time()
    p = subprocess.run([PY, TRAIN, *args], env=env, capture_output=True, text=True)
    tail = (p.stdout + p.stderr).strip().splitlines()[-4:]
    log(f"{char} {' '.join(args)}: exit {p.returncode} in {time.time() - t:.0f}s | " + " / ".join(tail))
    return p.returncode == 0


os.makedirs(os.path.dirname(LOG), exist_ok=True)
log("=== train all: probe first ===")
if not run("yannah", "probe"):
    log("PROBE FAILED -- nothing long started")
    sys.exit(1)
for c in ORDER:
    if not run(c, "train", str(STEPS)):
        log(f"STOPPED at {c}")
        sys.exit(1)
log("=== all trained ===")
