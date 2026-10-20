"""Start the bake-off once both downloads are complete AND byte-exact (sizes from Hugging Face) with a GGUF header."""
import os
import subprocess
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
C = os.path.join(ROOT, "models", "candidates")
WANT = {"Huihui-Qwen3.8-27B-abliterated.i1-IQ3_M.gguf": 12768332192,
        "TheDrummer_Cydonia-24B-v4.3-IQ4_XS.gguf": 12758916512}
LOG = os.path.join(ROOT, "data", "video_queue", "model_test_wait.log")


def ok(name: str, approx: int) -> bool:
    p = os.path.join(C, name)
    if not os.path.isfile(p) or os.path.getsize(p) != approx:
        return False
    with open(p, "rb") as fh:
        return fh.read(4) == b"GGUF"


start = time.time()
while not all(ok(n, s) for n, s in WANT.items()):
    if time.time() - start > 3 * 3600:
        open(LOG, "a").write("downloads did not finish in 3 h -- bake-off not started\n")
        raise SystemExit
    time.sleep(30)
time.sleep(60)                                  # let curl close the files
open(LOG, "a").write(time.strftime("%H:%M:%S") + " both files complete -- starting the bake-off\n")
subprocess.run([os.path.join(ROOT, "venv", "Scripts", "python.exe"),
                os.path.join(ROOT, "scripts", "model_bakeoff_2026_10_07.py")], cwd=ROOT)
