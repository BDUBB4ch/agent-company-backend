"""One-shot: restart the backend at the first moment NO render and NO Ilnora build is running (the gap between two
of her videos), so new code loads without killing a render. Preflight must pass. Gives up after 36 h. Exits after one
restart. Log: data/restart_when_idle.log. (2026-10-04: her repeat/Long send-backs were written mid-build.)"""
import datetime
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLAGS = [os.path.join(ROOT, "data", "video_rendering.flag"), os.path.join(ROOT, "data", "reel_building.flag")]
LOG = os.path.join(ROOT, "data", "restart_when_idle.log")
PY = os.path.join(ROOT, "venv", "Scripts", "python.exe")


def log(m: str) -> None:
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {m}\n")


def idle() -> bool:
    return not any(os.path.exists(f) for f in FLAGS)


def main() -> None:
    log("waiting for a gap with no render and no build")
    deadline = time.time() + 36 * 3600
    while time.time() < deadline:
        if idle():
            time.sleep(5)
            if not idle():                       # her next build just grabbed the card
                continue
            p = subprocess.run([PY, os.path.join(ROOT, "scripts", "preflight_check.py")], capture_output=True, text=True)
            if p.returncode != 0:
                log("preflight FAILED -- not restarting:\n" + (p.stdout + p.stderr)[-1500:])
                return
            subprocess.run(["powershell", "-NoProfile", "-Command",
                            "$c = Get-NetTCPConnection -LocalPort 8420 -State Listen -ErrorAction SilentlyContinue; "
                            "if ($c) { Stop-Process -Id $c.OwningProcess -Force }"], capture_output=True)
            log("restarted (watchdog revives it); done")
            return
        time.sleep(10)
    log("gave up after 36 h without a gap")


if __name__ == "__main__":
    main()
