"""MAKE VIVIAN'S CHOSEN HOME CANON -- her words, no model in the path.

She was asked (scripts/vivian_pick_her_home_2026_09_18.py) which of her three
places is real. She answered `HOME: C` -- the Peckham flat -- and wrote it out
in a tidied 361-word version of her own, which the ask explicitly allowed.

WHY THIS SCRIPT EXISTS INSTEAD OF RE-RUNNING THE ASK: the second run of that
same prompt wandered off into ad-banner concepts (a work seat, a work shelf,
and generation variance -- the n=1 lesson). The guard refused to write, which
was correct. Re-asking a third time would have cost another GPU turn and could
have produced a third different wording. Her answer already exists, captured
in the first run's console output, so THAT is what gets filed.

The console file is cp1252 and its only non-ascii bytes are four 0x92s --
cp1252 for U+2019, the apostrophe in her contractions. Decoding it as cp1252
recovers her text byte-for-byte; nothing is reconstructed or guessed. The
script asserts that before it writes, and refuses if the file ever contains a
byte it cannot map back.
"""
import json, re, sqlite3, datetime, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "brain.db"
CAPTURE = pathlib.Path(
    r"C:\Users\Owner\AppData\Local\Temp\claude"
    r"\C--Users-Owner-Desktop-AgentCompanyBackend"
    r"\85647a50-f8d1-4781-96ec-db8a518a1a85\tasks\bsvwyey3v.output")

DEN, HOXTON, PECKHAM = 1597, 1598, 1783

raw = CAPTURE.read_bytes()
odd = sorted({b for b in raw if b > 127})
assert odd == [0x92], f"unexpected non-ascii bytes {odd} -- do not guess, stop"
txt = raw.decode("cp1252")

m = re.search(r"^HOME:\s*([ABC]|NEW)\s*$", txt, re.M)
if not m:
    sys.exit("no HOME: line in the capture")
choice = m.group(1)
body = txt[m.end():]
body = body.split("=" * 70)[0]                 # stop at the console rule
body = re.sub(r"^\s*-{3,}\s*", "", body.strip())   # drop her leading ---
body = body.strip()

assert choice == "C", f"capture says {choice}, expected C"
assert body.startswith("I live in Peckham"), body[:80]
assert "\u2019" in body, "apostrophes did not survive the decode"
assert "terrazzo" not in body.lower()
assert 1500 < len(body) < 3000, len(body)
print(f"her choice: {choice} -- {len(body)} chars, apostrophes intact")

stamp = datetime.datetime.now().strftime("%Y-%m-%d")
canon = (
    "MY-HOME\n"
    "USE WHEN: your home, your place, where you live, being at home, off the "
    "clock at your place, what your place looks like.\n\n"
    "YOUR HOME (Vivian) -- your own words. You had described three different "
    f"places on three different nights; asked on {stamp} which one was real, "
    "you chose the Peckham flat and wrote it out as it reads below. This is "
    "the only one on record now.\n\n"
    + body + "\n")

with sqlite3.connect(DB) as c:
    c.row_factory = sqlite3.Row
    rows = [dict(c.execute("SELECT * FROM facts WHERE id=?", (i,)).fetchone())
            for i in (DEN, HOXTON, PECKHAM)]
    (ROOT / "data" / f"backup_vivian_three_homes_{stamp}.json").write_text(
        json.dumps(rows, indent=1, default=str), encoding="utf-8")

    c.execute("UPDATE facts SET content=? WHERE id=?", (canon, DEN))
    # the two docs that named the OTHER flats -- retired, never deleted
    for fid in (HOXTON, PECKHAM):
        c.execute("UPDATE facts SET status='superseded' WHERE id=?", (fid,))
    c.commit()

    live = c.execute("SELECT content FROM facts WHERE id=?", (DEN,)).fetchone()[0]
    assert body in live, "her words did not land verbatim -- CHECK fact 1597"
    still = c.execute(
        "SELECT id, source_name FROM facts WHERE category='private:Creative' "
        "AND status='active' AND (source_name LIKE 'my-home%' "
        "OR source_name LIKE 'me-at-home%')").fetchall()

print("fact 1597 rewritten; her text is in it verbatim")
print("active home docs:", [(r["id"], r["source_name"]) for r in still])
print(f"backup: data/backup_vivian_three_homes_{stamp}.json")
print("\nNOTE: assets/homes/creative.png is the TERRAZZO DEN -- it no longer "
      "matches her words. She can queue a new one herself (change_my_picture) "
      "on Barry's say-so.")
