"""Put back the thread rows the 10-17 wipe took that no brain backup had (the talks on the morning of 10-17, 02:47-11:30
local): the mind-with-barry journal kept them word for word, so each journal entry after the backup becomes its two
conversation rows again (channel personal, UTC = local + 6 h). The HOW-I-TALK relays (10:5x AM) are skipped -- their
sheets live in the personality files. Then each touched agent's rows are re-inserted in time order (reader sorts by id)."""
import datetime, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
import memory  # noqa: E402
import reflect  # noqa: E402

SN = "mind-with-barry-2026-10.md"
AGENT = {"private:Engineer": "engineer", "private:Creative": "creative", "private:ilnora": "ilnora", "private:BusinessOps": "business",
         "private:Operations": "operations", "private:Taliyah": "taliyah"}
STAMP = re.compile(r"^\[(\d\d)-(\d\d) (\d\d?):(\d\d) ([AP]M)\]\s*$", re.M)
CUT = datetime.datetime(2026, 10, 17, 2, 47)      # the backup; anything after it is missing from the threads
apply = "--apply" in sys.argv
added = {}
with memory.get_db() as c:
    for cat, aid in AGENT.items():
        first = reflect.HUMAN_NAMES.get(aid, aid.title())
        row = c.execute("SELECT content FROM facts WHERE category = ? AND source_name = ? AND status = 'active' ORDER BY id DESC LIMIT 1", (cat, SN)).fetchone()
        if not row:
            continue
        txt = row[0]; ms = list(STAMP.finditer(txt))
        for m, nxt in zip(ms, ms[1:] + [None]):
            mo, d, h, mi, ap = m.groups(); h = int(h) % 12 + (12 if ap == "PM" else 0)
            local = datetime.datetime(2026, int(mo), int(d), h, int(mi))
            if local <= CUT:
                continue
            body = txt[m.end(): nxt.start() if nxt else len(txt)].strip()
            mm = re.match(rf"Barry:\s*(.*?)\n{re.escape(first)}:\s*(.*)$", body, re.S)
            if not mm or mm.group(1).startswith("Barry, 2026-10-17:"):
                continue                                              # a relay of his words, not a talk
            user, agent = mm.group(1).strip(), mm.group(2).strip()
            ts = (local + datetime.timedelta(hours=6)).isoformat(timespec="microseconds") + "+00:00"
            dup = c.execute("SELECT 1 FROM conversations WHERE agent_id = ? AND role = 'user' AND content = ?", (aid, user)).fetchone()
            if dup:
                continue
            added.setdefault(aid, []).append((ts, user, agent))
    for aid, rows in added.items():
        print(f"{aid:10s}: +{len(rows)} exchanges  " + " | ".join(r[0][5:16] for r in rows))
        if apply:
            for ts, user, agent in rows:
                c.execute("INSERT INTO conversations (agent_id, role, content, timestamp, channel) VALUES (?, 'user', ?, ?, 'personal')", (aid, user, ts))
                c.execute("INSERT INTO conversations (agent_id, role, content, timestamp, channel) VALUES (?, 'agent', ?, ?, 'personal')",
                          (aid, agent, (datetime.datetime.fromisoformat(ts) + datetime.timedelta(seconds=30)).isoformat(timespec="microseconds")))
            allrows = c.execute("SELECT agent_id, role, content, timestamp, channel FROM conversations WHERE agent_id = ? ORDER BY timestamp, id", (aid,)).fetchall()
            c.execute("DELETE FROM conversations WHERE agent_id = ?", (aid,))
            c.executemany("INSERT INTO conversations (agent_id, role, content, timestamp, channel) VALUES (?, ?, ?, ?, ?)", allrows)
    if apply:
        c.commit()
print("APPLIED" if apply else "DRY RUN -- add --apply")
