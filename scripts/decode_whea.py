import os, struct, uuid
KNOWN = {"9876ccad-47b4-4bdb-b65e-16f193c4f3db": "Processor (generic)", "a5bc1114-6f64-4ede-b863-3e83ed7c83b1": "Memory",
         "d995e954-bbc1-430f-ad91-b44dcb3c6f35": "PCI Express", "c5753963-3b84-4095-bf78-eddad3f9c9dd": "PCI/PCI-X bus",
         "dc3ea0b0-a144-4797-b95b-53fa242b6e1d": "x86/x64 processor (MCA)", "81212a96-09ed-4996-9471-8d729c8e69ed": "Firmware error",
         "e8f56ffe-919c-4cc5-ba88-65abe14913bb": "PCI component", "6f3380d1-6eb0-497f-a578-4d4c65a16e7a": "DMAr generic"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for line in open(os.path.join(ROOT, "data", "crash_dumps", "whea_raw.txt"), encoding="utf-16" if open(os.path.join(ROOT, "data", "crash_dumps", "whea_raw.txt"), "rb").read(2) in (b"\xff\xfe",) else "utf-8"):
    line = line.strip()
    if not line: continue
    when, hexs = line.rsplit(" ", 1)
    b = bytes.fromhex(hexs.strip())
    if b[:4] != b"CPER": print(when, "not CPER"); continue
    nsec = struct.unpack_from("<H", b, 10)[0]; sev = struct.unpack_from("<I", b, 12)[0]
    print(when, "CPER sections:", nsec, "severity:", {0: "recoverable", 1: "fatal", 2: "corrected", 3: "informational"}.get(sev, sev))
    for i in range(nsec):
        off = 128 + 72 * i
        so, sl = struct.unpack_from("<II", b, off)
        guid = str(uuid.UUID(bytes_le=b[off + 16: off + 32]))
        print("   section", i, KNOWN.get(guid, guid), "len", sl)
        if KNOWN.get(guid) == "PCI Express":
            v = struct.unpack_from("<Q", b, so)[0]; ptype, ver = struct.unpack_from("<IBB", b, so + 8)[0], 0
            dev = b[so + 24: so + 24 + 16]
            vendor, device = struct.unpack_from("<HH", b, so + 56 - 32 + 24) if False else (None, None)
            print("      PCIe validation bits", hex(v), "port type", ptype, "id bytes", b[so + 16: so + 24].hex(), "devid", b[so+24:so+40].hex())
        if KNOWN.get(guid, "").startswith("x86"):
            v = struct.unpack_from("<Q", b, so)[0]; print("      MCA validation bits", hex(v))
            apic = struct.unpack_from("<Q", b, so + 8)[0]; print("      local APIC id", apic)
