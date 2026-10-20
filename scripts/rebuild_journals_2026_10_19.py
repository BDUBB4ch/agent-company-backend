"""Rebuild every seat's mind-with-barry-2026-10 journal without the 2026-10-17 voice-measurement turns.
The journal is a rolling monthly fact (~18K cap): each append supersedes the last version and the OLDEST entries fall
off. My 12-20 measurement entries per seat pushed every real talk out of the active version. The real entries survive
in the superseded versions and in the 10-17 02:47 brain backup. Here: gather every entry block from every version
(backup + live), drop the ones whose first 'Barry:' line is a measurement prompt, dedupe, sort by stamp, rebuild.
Usage: ... [--apply]"""
import os, re, sqlite3, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
import config, memory  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from voice_distance_2026_10_17 import PROMPTS  # noqa: E402

SRC = os.path.join(config.DATA_DIR, "backup_brain_before_sophie_mp_skills_2026-10-17.db")
SN = "mind-with-barry-2026-10.md"
STAMP = re.compile(r"^\[(\d\d)-(\d\d) (\d\d?):(\d\d) ([AP]M)\]\s*$", re.M)
apply = "--apply" in sys.argv


def blocks(txt):
    ms = list(STAMP.finditer(txt))
    out = []
    for m, nxt in zip(ms, ms[1:] + [None]):
        b = txt[m.start(): nxt.start() if nxt else len(txt)].rstrip() + "\n\n"
        mo, d, h, mi, ap = m.groups()
        h = int(h) % 12 + (12 if ap == "PM" else 0)
        out.append(((int(mo), int(d), h, int(mi)), b))
    return out


def gather(conn):
    found = {}
    for cat, txt in conn.execute("SELECT category, content FROM facts WHERE source_name = ? ORDER BY id", (SN,)):
        for key, b in blocks(txt):
            m = re.search(r"^Barry:\s*(.+?)\s*$", b, re.M)
            if m and m.group(1).strip() in PROMPTS:
                continue
            found.setdefault(cat, {})[(key, b[:90])] = (key, b)
    return found


real = gather(sqlite3.connect(SRC))
with memory.get_db() as live:
    for cat, d in gather(live).items():
        real.setdefault(cat, {}).update(d)
    for cat in sorted(real):
        row = live.execute("SELECT id, content FROM facts WHERE category = ? AND source_name = ? AND status = 'active' "
                           "ORDER BY id DESC LIMIT 1", (cat, SN)).fetchone()
        if not row:
            print(f"{cat:24s}: no active journal"); continue
        fid, cur = row
        head = cur[:STAMP.search(cur).start()].rstrip() if STAMP.search(cur) else cur.rstrip()
        entries = sorted(real[cat].values(), key=lambda kb: kb[0])
        new = head + "\n\n" + "".join(b for _, b in entries).rstrip() + "\n"
        stamps = [f"{k[0]:02d}-{k[1]:02d} {k[2]:02d}:{k[3]:02d}" for k, _ in entries]
        print(f"{cat:24s} #{fid}: {len(entries)} real entries, {len(new)} chars, {stamps[0] if stamps else '-'} .. {stamps[-1] if stamps else '-'}")
        for k, b in entries:
            if (k[0], k[1]) == (10, 17):
                print("     10-17 entry:", " ".join(b.split())[:150])
        if apply:
            live.execute("UPDATE facts SET content = ? WHERE id = ?", (new, fid))
    if apply:
        live.commit()
print("APPLIED" if apply else "DRY RUN -- add --apply")
