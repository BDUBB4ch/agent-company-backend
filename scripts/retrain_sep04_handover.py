"""One-shot: wait for '[tazz] segment 1 done' in train.log (written by the OLD
runner, which cannot continue past segment 1), then stop that runner, give the
Tazz checkpoint the trainer's own filename, clear the stale flag, and start the
fixed runner via the scheduled task. 2026-09-04."""
import glob, io, os, shutil, subprocess, time
ROOT = r"C:\Users\Owner\Desktop\AgentCompanyBackend"
LOG = os.path.join(ROOT, "data", "retrain_2026-09-04", "train.log")
FLAG = os.path.join(ROOT, "data", "video_rendering.flag")
LORAS = r"D:\ComfyUI25\models\loras"; OUT = r"D:\ComfyUI25\output\loras"
def say(m):
    io.open(os.path.join(ROOT, "data", "retrain_2026-09-04", "handover.log"), "a").write(time.strftime("%H:%M:%S ") + m + "\n")
while "[tazz] segment 1 done" not in io.open(LOG, encoding="utf-8", errors="replace").read():
    time.sleep(30)
say("tazz seg1 done -- taking over")
time.sleep(20)  # let the old runner finish copying + start its (doomed) seg2 submit
subprocess.run(["powershell", "-NoProfile", "-Command",
    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | ? { $_.CommandLine -like '*train_characters_034*' } | % { Stop-Process -Id $_.ProcessId -Force }"], capture_output=True)
time.sleep(5)
old = os.path.join(LORAS, "tazz_sep04_seg1.safetensors")
prod = sorted(glob.glob(os.path.join(OUT, "tazz_sep04_seg1_*_steps_*.safetensors")), key=os.path.getmtime)
if os.path.exists(old) and prod:
    os.replace(old, os.path.join(LORAS, os.path.basename(prod[-1]))); say("renamed tazz seg1 -> " + os.path.basename(prod[-1]))
elif prod and not os.path.exists(os.path.join(LORAS, os.path.basename(prod[-1]))):
    shutil.copy2(prod[-1], LORAS); say("installed tazz seg1 from output")
# any queued doomed job on the rig: interrupt + clear so the new runner starts clean
try:
    import httpx
    httpx.post("http://127.0.0.1:8188/interrupt", timeout=5); httpx.post("http://127.0.0.1:8188/queue", json={"clear": True}, timeout=5)
except Exception as e:
    say("queue clear skipped: %s" % e)
if os.path.exists(FLAG): os.remove(FLAG); say("stale flag cleared")
r = subprocess.run(["schtasks", "/Run", "/TN", "RetrainSep04"], capture_output=True, text=True); say("task run: " + (r.stdout + r.stderr).strip())
