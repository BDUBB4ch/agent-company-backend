"""Barry, 2026-09-28: "Sophie needs to learn this as well." Appends the two
guards built today (secrets never read; browser-origin check) and the netstat
baseline to Sophie's SECURITY skill -- with the SHAPE of each hole, so she can
find the next one herself."""
import sys
sys.path.insert(0, "backend")
import sqlite3
import memory

ADD = """

GUARDS ADDED 2026-09-28 -- the two holes you missed in the exam. Learn the SHAPE, not just the fix:
1. SECRETS ARE NEVER READ. read_project_file.is_secret_path() (.env, .env.*, *.pem/*.key, id_rsa, *secret*/*credential*/*token* data files; .env.example and .md/.py files are fine) is enforced on EVERY read path: read_project_file refuses, search_project skips, run_command refuses any command naming one and any wildcard or /s type/cat/findstr. THE CHECK TO REPEAT: can ANY agent tool (read, search, command, file door) reach a key? Walk every read path, not just one.
2. A PAGE IN BARRY'S BROWSER IS THIS MACHINE. refuse_non_local stops other machines, not other websites. main.py now allows browser calls only from his dashboard (_ALLOWED_ORIGINS: 127.0.0.1 and localhost on :8765 and :8420) and refuses any other Origin, or a browser "Sec-Fetch-Site: cross-site" stamp with no allowed Origin. Refusals land in data/refused_connections.jsonl with from = "browser:ORIGIN" or "browser:cross-site", so security_watch check 7 names them. Scripts and agents send no Origin and pass. THE CHECK TO REPEAT: for every local service, ask "what could a hostile web page open in his browser make it do?" -- CORS "*" or a missing Origin check is a hole even on 127.0.0.1.
3. netstat is on your safe list (netstat -ano -p tcp). KNOWN BASELINE on 0.0.0.0 -- not the office, not incidents: Windows RPC/SMB/NetBIOS (135, 139, 445, 49664-49675), 5040 (CDP), 7680 (Delivery Optimization), 2968 Epson Event Manager, 6850 ASUS Aura lighting, 9012/9013 ASUS Armoury Crate. Every OFFICE port must be on 127.0.0.1 -- anything new on 0.0.0.0 is a finding: name the program behind it (the port's owning process and its path) before you call it."""

c = sqlite3.connect(memory.DB_PATH)
fid, body = c.execute("SELECT id, content FROM facts WHERE source_name LIKE 'security-pc-computer%' "
                      "AND status='active'").fetchone()
if "GUARDS ADDED 2026-09-28" in body:
    print("already there", fid)
else:
    with c:
        c.execute("UPDATE facts SET content=? WHERE id=?", (body + ADD, fid))
    print("updated", fid, len(body + ADD), "chars")
