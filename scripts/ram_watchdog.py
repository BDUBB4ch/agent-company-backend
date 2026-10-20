"""RAM WATCHDOG (2026-09-25). Both PC crashes (09-23, 09-24) and tonight's near-miss (0.7 GB free) happened while
ComfyUI loaded the 12.3 GB Z-Image training model. This checks free physical RAM every second and KILLS ComfyUI
(the owner of port 8188) the moment free RAM drops under the floor -- a lost training run instead of a crashed PC.
    venv/Scripts/python.exe scripts/ram_watchdog.py [floor_gb=5] [hours=14]
Log: data/zimage_lora/ram_watchdog.log"""
import ctypes
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "data", "zimage_lora", "ram_watchdog.log")
FLOOR = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
HOURS = float(sys.argv[2]) if len(sys.argv) > 2 else 14.0


class MS(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def free_gb():
    m = MS()
    m.dwLength = ctypes.sizeof(MS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullAvailPhys / 1e9


def log(msg):
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(f"{time.strftime('%m-%d %H:%M:%S')} {msg}\n")


def kill_comfy():
    ps = ("$c=Get-NetTCPConnection -LocalPort 8188 -State Listen -ErrorAction SilentlyContinue; "
          "if($c){Stop-Process -Id $c.OwningProcess -Force; 'killed ' + $c.OwningProcess}")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return (r.stdout or "").strip()


log(f"start: floor {FLOOR} GB, {HOURS} h, free now {free_gb():.1f} GB")
low, end, last_note = 1e9, time.time() + HOURS * 3600, 0
while time.time() < end:
    f = free_gb()
    low = min(low, f)
    if f < FLOOR:
        log(f"FREE RAM {f:.1f} GB < {FLOOR} -- {kill_comfy() or 'no ComfyUI to kill'}")
        time.sleep(15)
    elif time.time() - last_note > 600:
        log(f"ok: free {f:.1f} GB (lowest so far {low:.1f})")
        last_note = time.time()
    time.sleep(1)
log(f"stop: lowest free RAM seen {low:.1f} GB")
