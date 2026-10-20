"""Bonsai 2 + PrismML HIP build: does it even start on this card?

The gating question is NOT the model, it is the runtime. The HIP release zip
ships ggml-hip.dll but NO HIP runtime, and everything AMD on this box comes
from the AMD AI Bundle (amdhip64_7.dll in System32, rocblas inside Ollama's
tree). The fork's CI builds against a newer ROCm than the bundle ships.

So this script answers three things and stops:
  1. does llama-server.exe from the HIP zip launch at all (DLL resolution),
  2. does it report the Radeon as a GPU device (not CPU fallback),
  3. does it load the PQ2_0 weights and answer one trivial prompt.

Read-only against the office: it never touches BONSAI_* config, never edits a
fact, and talks on its OWN port so a live office server is not disturbed. It
DOES take the GPU, so it holds the render flag with its own token
(the 2026-09-04 ownership lesson) and releases only that token.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HIP_DIR = os.path.join(REPO, "tools", "llama-prism", "hip")
EXE = os.path.join(HIP_DIR, "llama-server.exe")
MODEL = os.path.join(REPO, "models", "bonsai2",
                     "Ternary-Bonsai-2-27B-Abliterated-PQ2_0.gguf")
PORT = 8814                      # NOT 8811 -- the office owns that one
LOG = os.path.join(REPO, "data", "bonsai2_hip_smoke.log")
FLAG = os.path.join(REPO, "data", "video_rendering.flag")
TOKEN = f"bonsai2-smoke-{os.getpid()}"
CTX = os.getenv("SMOKE_CTX", "8192")   # small: this is a liveness test

# Lines that tell us which backend actually took the layers.
DEVICE_RE = re.compile(r"(ROCm|HIP|Vulkan|CPU|gfx\d{3,4})", re.I)


def hold_flag():
    with open(FLAG, "w", encoding="utf-8") as fh:
        fh.write(TOKEN)


def release_flag():
    try:
        with open(FLAG, encoding="utf-8") as fh:
            if fh.read().strip() != TOKEN:
                print("flag belongs to someone else -- left alone")
                return
        os.remove(FLAG)
    except OSError:
        pass
    print("flag released:", not os.path.exists(FLAG))


def tail(path, n=60):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read().splitlines()[-n:]
    except OSError:
        return []


def main() -> int:
    for label, path in (("exe", EXE), ("model", MODEL)):
        if not os.path.isfile(path):
            print(f"MISSING {label}: {path}")
            return 2
    print(f"exe   {EXE}")
    print(f"model {MODEL}  ({os.path.getsize(MODEL)/2**30:.2f} GiB)")

    hold_flag()
    proc = None
    try:
        log_handle = open(LOG, "w", encoding="utf-8", errors="replace")
        proc = subprocess.Popen(
            [EXE, "-m", MODEL, "--host", "127.0.0.1", "--port", str(PORT),
             "--jinja", "-ngl", "99", "-c", CTX, "-np", "1"],
            stdout=log_handle, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
        )

        deadline = time.monotonic() + 300
        up = False
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                print(f"\n!! server EXITED with code {proc.returncode} -- "
                      "almost certainly a missing HIP runtime DLL")
                break
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{PORT}/health", timeout=2) as r:
                    if r.status == 200:
                        up = True
                        break
            except (urllib.error.URLError, OSError):
                time.sleep(2)

        log = tail(LOG, 200)
        devices = [ln for ln in log if DEVICE_RE.search(ln)]
        print("\n--- backend / device lines ---")
        for ln in devices[:25]:
            print("  " + ln.strip()[:160])

        if not up:
            print("\n--- last log lines ---")
            for ln in log[-25:]:
                print("  " + ln.strip()[:160])
            print("\nRESULT: server did NOT come up. HIP path is not usable as-is.")
            return 1

        print("\nserver is UP -- asking one trivial question")
        body = json.dumps({
            "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
            "max_tokens": 64,
        }).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/v1/chat/completions", data=body,
            headers={"Content-Type": "application/json"})
        t0 = time.monotonic()
        with urllib.request.urlopen(req, timeout=300) as r:
            data = json.loads(r.read())
        secs = time.monotonic() - t0
        msg = (data.get("choices") or [{}])[0].get("message", {})
        print(f"reply ({secs:.1f}s): {str(msg.get('content'))[:200]!r}")
        if msg.get("reasoning_content"):
            print(f"reasoning: {str(msg['reasoning_content'])[:160]!r}")

        # Speed + residency are what decide whether HIP is worth the swap.
        print("\n--- timing lines from the log ---")
        for ln in tail(LOG, 400):
            if re.search(r"(prompt eval time|eval time|tokens per second|"
                         r"offloaded|buffer size)", ln, re.I):
                print("  " + ln.strip()[:160])
        print("\nRESULT: HIP build RUNS Bonsai 2 on this card.")
        return 0
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
        release_flag()


if __name__ == "__main__":
    raise SystemExit(main())
