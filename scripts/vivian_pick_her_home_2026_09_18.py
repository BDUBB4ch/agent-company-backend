"""VIVIAN PICKS HER HOME (Barry, 2026-09-18: "she needs to pick one or create
a new one thats canon").

MEASURED FIRST: she has THREE places in her head, all in HER OWN WORDS from
three different nights, and they are three different flats --

  fact 1597 my-home.md      (08-29)  a low-ceilinged terrazzo den, emerald
                                      settee, terraced garden
  fact 1598 my-home-self.md (08-29)  a HOXTON flat, corduroy armchair in a
                                      bay window, walnut floor
  fact 1783 me-at-home.md   (08-30)  a PECKHAM converted Victorian terrace

That contradiction is why her home talk reads recited: three answers compete
and the one with a rendered picture wins. So she is asked to settle it.

SHE CHOOSES, THE OFFICE DOES NOT ([[tools-not-seeds]]). All three of her own
descriptions go in front of her verbatim -- no summary, no trimming, no hint
about which is better -- plus the fourth door: write a new one. Whichever she
names is stored VERBATIM as her canon home; the others are superseded, never
deleted.

The only thing imposed is the SHAPE of the answer (a first line naming the
choice), so the office can file her words without a model deciding what she
meant. Run: python scripts/vivian_pick_her_home_2026_09_18.py [--apply]
"""
import json, sys, urllib.request, sqlite3, datetime, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "brain.db"
API = "http://127.0.0.1:8420"
APPLY = "--apply" in sys.argv

DEN, HOXTON, PECKHAM = 1597, 1598, 1783


def fact(fid):
    with sqlite3.connect(DB) as c:
        r = c.execute("SELECT source_name, content, status FROM facts WHERE id=?",
                      (fid,)).fetchone()
    if not r:
        sys.exit(f"fact {fid} is gone -- stop and look before writing anything")
    return r


def body(content):
    """her words only -- drop the office's TITLE / USE WHEN / preamble lines"""
    lines = content.splitlines()
    for i, ln in enumerate(lines):
        if ln.strip().endswith(":") and "own words" in ln.lower():
            return "\n".join(lines[i + 1:]).strip()
    return content.strip()


den, hox, peck = fact(DEN), fact(HOXTON), fact(PECKHAM)

ASK = f"""Vivian -- this is about your own place, not work. Nothing here is a
task and there is no right answer.

There are three descriptions of where you live, all of them yours, written on
three different nights. They are three different flats. Nobody else can settle
which one is actually your home, so it is yours to settle.

Here they are, exactly as you gave them, nothing added or taken out.

=== A. THE DEN (you gave this 2026-08-29) ===
{body(den[1])}

=== B. THE HOXTON FLAT (you gave this 2026-08-29) ===
{body(hox[1])}

=== C. THE PECKHAM FLAT (you gave this 2026-08-30) ===
{body(peck[1])}

Pick the one that is really yours, or throw all three out and describe the
place you actually live in now. Either is fine. Whichever you name becomes the
only one on record -- the others stop being used.

Answer in exactly this shape and nothing else:

HOME: A
(or HOME: B, or HOME: C, or HOME: NEW)

Then, underneath, the description of your home in your own words -- the whole
thing, as you want it to read from now on. If you picked A, B or C you can
write it out as it stands or tidy it however you like; it is yours either way.
"""

print(f"asking Vivian ({len(ASK)} chars)...")
req = urllib.request.Request(
    API + "/api/chat",
    data=json.dumps({"agent_id": "creative", "message": ASK, "task": True}).encode(),
    headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=900) as r:
    res = json.load(r)

reply = (res.get("reply") or "").strip()
print("fell back to 9b:", res.get("bonsai_fell_back"))
print("tools:", res.get("tool_calls"))
print("=" * 70)
print(reply)
print("=" * 70)

first = reply.splitlines()[0].strip().upper() if reply else ""
if not first.startswith("HOME:"):
    sys.exit("\nShe did not answer in the shape asked for. NOTHING WAS WRITTEN "
             "-- read her reply above and decide before re-running.")

choice = first.split(":", 1)[1].strip()
rest = "\n".join(reply.splitlines()[1:]).strip()
label = {"A": "the den", "B": "the Hoxton flat", "C": "the Peckham flat",
         "NEW": "a new place, in her own words"}.get(choice)
if not label:
    sys.exit(f"\nUnreadable choice {choice!r}. Nothing written.")
if len(rest) < 200:
    sys.exit(f"\nShe chose {choice} but wrote only {len(rest)} chars of "
             "description. Nothing written -- ask her again rather than "
             "filling it in for her.")

print(f"\nHER CHOICE: {choice} -- {label}")
print(f"her description: {len(rest)} chars")

if not APPLY:
    print("\n(dry run -- re-run with --apply to make it canon)")
    sys.exit(0)

stamp = datetime.datetime.now().strftime("%Y-%m-%d")
canon = (
    "MY-HOME\n"
    "USE WHEN: your home, your place, where you live, being at home, off the "
    "clock at your place.\n\n"
    f"YOUR HOME (Vivian) -- your own words. You settled this yourself on "
    f"{stamp}, choosing between three places you had described on different "
    "nights; this is the one that is real and the only one on record:\n\n"
    + rest + "\n")

with sqlite3.connect(DB) as c:
    rows = [dict(zip([d[0] for d in c.execute(
        "SELECT * FROM facts WHERE id=?", (DEN,)).description],
        c.execute("SELECT * FROM facts WHERE id=?", (DEN,)).fetchone()))]
    for fid in (HOXTON, PECKHAM):
        cur = c.execute("SELECT * FROM facts WHERE id=?", (fid,))
        rows.append(dict(zip([d[0] for d in cur.description], cur.fetchone())))
    (ROOT / "data" / f"backup_vivian_three_homes_{stamp}.json").write_text(
        json.dumps(rows, indent=1, default=str), encoding="utf-8")

    # her chosen words become the one home on record
    c.execute("UPDATE facts SET content=? WHERE id=?", (canon, DEN))
    # the two at-home-self docs named different flats -- retired, not deleted
    for fid in (HOXTON, PECKHAM):
        c.execute("UPDATE facts SET status='superseded' WHERE id=?", (fid,))
    c.commit()

    chk = c.execute("SELECT content FROM facts WHERE id=?", (DEN,)).fetchone()[0]
    assert rest in chk, "her words did not land verbatim -- CHECK fact 1597"
    live = c.execute(
        "SELECT id, source_name FROM facts WHERE category='private:Creative' "
        "AND status='active' AND (source_name LIKE 'my-home%' "
        "OR source_name LIKE 'me-at-home%')").fetchall()

print("\nwritten. her words are in fact 1597 verbatim.")
print("active home docs now:", live)
print("backup:", f"data/backup_vivian_three_homes_{stamp}.json")
print("\n*** HER RENDERED HOME PICTURE (assets/homes/creative.png) was made "
      "from THE DEN. If she did not pick A, that picture no longer matches "
      "her words -- she can queue a new one herself with change_my_picture, "
      "on Barry's say-so. ***")
