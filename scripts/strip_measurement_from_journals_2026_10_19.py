"""Remove the voice-measurement turns (2026-10-17) from every seat's mind-with-barry-2026-10 journal. The five test
prompts went out on the personal channel, so each one was appended verbatim as a talk with Barry; the thread rows were
purged, the journal entries were not. An entry is removed only when its first 'Barry:' line IS one of the five prompts.
Usage: ... [--apply]"""
import os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
import memory  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from voice_distance_2026_10_17 import PROMPTS  # noqa: E402

apply = "--apply" in sys.argv
STAMP = re.compile(r"^\[\d\d-\d\d \d\d?:\d\d [AP]M\]\s*$", re.M)
with memory.get_db() as c:
    rows = c.execute("SELECT id, category, content FROM facts WHERE source_name = 'mind-with-barry-2026-10.md' "
                     "AND status = 'active' ORDER BY id").fetchall()
    for fid, cat, txt in rows:
        starts = [m.start() for m in STAMP.finditer(txt)]
        if not starts:
            print(f"{cat:24s} #{fid}: no entries"); continue
        head = txt[:starts[0]]
        blocks = [txt[s:e] for s, e in zip(starts, starts[1:] + [len(txt)])]
        keep, drop = [], 0
        for b in blocks:
            m = re.search(r"^Barry:\s*(.+?)\s*$", b, re.M)
            if m and m.group(1).strip() in PROMPTS:
                drop += 1
            else:
                keep.append(b)
        print(f"{cat:24s} #{fid}: {len(blocks)} entries, {drop} measurement, {len(keep)} real kept")
        if apply and drop:
            new = (head.rstrip() + "\n\n" + "".join(keep).strip() + "\n") if keep else head.rstrip() + "\n"
            c.execute("UPDATE facts SET content = ? WHERE id = ?", (new, fid))
    if apply:
        c.commit()
print("APPLIED" if apply else "DRY RUN -- add --apply")
