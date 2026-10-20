"""Read the Windows crash dumps copied to data/crash_dumps (read-only, no GPU). 2026-10-12.
Prints per dump: bugcheck code + parameters, and the drivers (.sys) named in it, flagging GPU/storage/network ones."""
import glob
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAMES = {0x116: "VIDEO_TDR_FAILURE", 0x7E: "SYSTEM_THREAD_EXCEPTION_NOT_HANDLED", 0x3B: "SYSTEM_SERVICE_EXCEPTION",
         0x4E: "PFN_LIST_CORRUPT", 0x154: "UNEXPECTED_STORE_EXCEPTION", 0x9F: "DRIVER_POWER_STATE_FAILURE"}
HOT = re.compile(r"amd|atikmd|dxg|ntfs|stor|nvme|ndis|netwtw|rt\d|e1|bth|usb|wdf|fltmgr|ks\.sys|win32k|hal\.dll|pci|acpi|intel|iaStor|npu", re.I)

for f in sorted(glob.glob(os.path.join(ROOT, "data", "crash_dumps", "*.dmp"))):
    b = open(f, "rb").read()
    print("==", os.path.basename(f), len(b), "bytes", b[:8])
    if b[:8] == b"PAGEDU64":
        code = struct.unpack_from("<I", b, 0x38)[0]
        params = struct.unpack_from("<4Q", b, 0x40)
        print("  bugcheck", hex(code), NAMES.get(code, ""), [hex(p) for p in params])
    elif b[:4] == b"MDMP":
        print("  user-mode minidump (unexpected)")
    uni = re.findall(rb"(?:[A-Za-z0-9_\-\.]\x00){3,40}\.\x00(?:s\x00y\x00s|d\x00l\x00l)\x00", b)
    names = sorted({u.decode("utf-16le").lower() for u in uni})
    asc = sorted({m.decode().lower() for m in re.findall(rb"[A-Za-z0-9_\-]{3,30}\.sys", b)})
    allnames = sorted(set(names) | set(asc))
    print("  drivers named:", len(allnames))
    print("  of interest:", [n for n in allnames if HOT.search(n)][:40])


# --- who owns the faulting address? KLDR_DATA_TABLE_ENTRY scan: DllBase @+0x30, SizeOfImage @+0x40 --------------------
def modules(b):
    out = {}
    n = len(b)
    for m in re.finditer(rb"(?:[A-Za-z0-9_\-\.]\x00){3,40}\.\x00(?:s\x00y\x00s|d\x00l\x00l|e\x00x\x00e)\x00", b):
        name = m.group(0).decode("utf-16le").lower()
        # an entry's name buffer sits shortly after the entry itself: look back up to 0x400 bytes for base/size pairs
        lo = max(0, m.start() - 0x400)
        for off in range(lo, m.start(), 8):
            base = struct.unpack_from("<Q", b, off)[0] if off + 8 <= n else 0
            if base >> 44 == 0xfffff and base & 0xfff == 0 and off + 0x10 <= n:
                size = struct.unpack_from("<I", b, off + 0x10)[0]
                if 0x1000 <= size <= 0x4000000 and (off - 0x30) >= 0:
                    out.setdefault(name, set()).add((base, size))
    return out


print("\n=== owner of the fault address (parameter 2 of 0x3B/0x7E; 0x116 uses parameter 2 = the driver's TDR routine)")
for f in sorted(glob.glob(os.path.join(ROOT, "data", "crash_dumps", "*.dmp"))):
    b = open(f, "rb").read()
    code = struct.unpack_from("<I", b, 0x38)[0] & 0xffff
    addr = struct.unpack_from("<Q", b, 0x48)[0]
    hits = sorted({nm for nm, bs in modules(b).items() for base, size in bs if base <= addr < base + size})
    print(os.path.basename(f), hex(code), hex(addr), "->", hits or "no match")
