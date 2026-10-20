import glob, os, re
R = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "crash_dumps", "analysis")
KEYS = re.compile(r"^(BUGCHECK_CODE|BUGCHECK_P\d|PROCESS_NAME|IMAGE_NAME|MODULE_NAME|FAULTING_MODULE|FAILURE_BUCKET_ID|SYMBOL_NAME|STACK_COMMAND|MODULE_NAME|DEFAULT_BUCKET_ID|EXCEPTION_CODE_STR|FAULTING_IP|PROBABLY_CAUSED_BY|Image path|Timestamp|ProductVersion|FileVersion)\b|^ ?(Image path|Timestamp|File version|Product version)", re.I)
for f in sorted(glob.glob(os.path.join(R, "*.txt"))):
    b = open(f, "rb").read()
    t = b.decode("utf-16le", "ignore") if b[:2] in (b"\xff\xfe",) or b.count(b"\x00") > len(b) // 3 else b.decode("utf-8", "ignore")
    print("==", os.path.basename(f))
    seen = set()
    for l in t.splitlines():
        l = l.strip()
        if KEYS.search(l) and l not in seen:
            seen.add(l); print("  ", l[:170])
    st = re.search(r"STACK_TEXT:\s*\n((?:.*\n){1,14})", t)
    if st: print("   STACK:\n" + "\n".join("     " + x[:150] for x in st.group(1).splitlines()[:12]))
