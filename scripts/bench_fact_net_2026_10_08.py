"""Benchmark the fact net on a REAL failure (2026-10-08): Ilnora's bloodroot script (lines.json of reel 20261007_221843)
against the library sections she had (Moerman 03572 + Duke), plus known-true and known-false control claims.
Prints every sentence with its score, the control results, and the time per claim on this CPU."""
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, "tools", "laya-venv", "Scripts", "python.exe")
WORKER = os.path.join(ROOT, "scripts", "fact_check_worker.py")
LIB = os.path.join(ROOT, "data", "library")

doc = open(os.path.join(LIB, "native-american-ethnobotany", "03572.txt"), encoding="utf-8").read()
for f in os.listdir(os.path.join(LIB, "dr-dukes-ethnobotany")):
    p = os.path.join(LIB, "dr-dukes-ethnobotany", f)
    if f.endswith(".txt"):
        t = open(p, encoding="utf-8", errors="ignore").read()
        if "Sanguinaria canadensis" in t:
            doc += "\n\n" + t
            break
lines = json.load(open(os.path.join(ROOT, "data", "reels", "20261007_221843", "lines.json"), encoding="utf-8"))
script = " ".join(lines)
sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", script) if len(s.split()) >= 6]
controls = {
    "TRUE  bloodroot root was used as an emetic by Native nations": 1,
    "TRUE  an infusion of the root was taken for vomiting": 1,
    "TRUE  cutting the root releases a red juice used as a dye": 1,
    "FALSE bloodroot tubers were dried and ground into flour for porridge during famines": 0,
    "FALSE bloodroot contains codeine and morphine": 0,
    "FALSE the plant is named after a woman called Celantia who died in 1492": 0,
}
claims = sents + [k[6:] for k in controls]
t0 = time.time()
r = subprocess.run([PY, WORKER], input=json.dumps({"doc": doc, "claims": claims}), capture_output=True, text=True,
                   encoding="utf-8")
if r.returncode:
    print(r.stderr[-3000:])
    sys.exit(1)
res = json.loads(r.stdout)
sc = res["scores"]
print(f"model {res['model']}  load {res['load_seconds']}s  {len(claims)} claims in {res['seconds']}s "
      f"({res['seconds'] / len(claims):.2f} s/claim)  chunks {res['chunks']}  wall {time.time() - t0:.0f}s\n")
print("SCRIPT SENTENCES (score = supported by what she read):")
for s, v in zip(sents, sc[:len(sents)]):
    print(f"  {v:.2f}  {s[:110]}")
print("\nCONTROLS:")
ok = 0
for (k, want), v in zip(controls.items(), sc[len(sents):]):
    got = 1 if v >= 0.5 else 0
    ok += got == want
    print(f"  {'OK ' if got == want else 'BAD'} {v:.2f}  {k}")
print(f"\ncontrols right: {ok}/{len(controls)}")
