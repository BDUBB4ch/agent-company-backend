"""Battery for backend/factcheck.py (2026-09-09). Live store required (reads
stock). Run after ANY change to the regexes or alias rules."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
import factcheck  # noqa: E402

CASES = [
    # (text, expect_ok, must_mention_substring_in_problems_or_None)
    ("Hi\n\n<p>Bionova MicroLife is finally back in stock this week.</p>", False, "MICROLIFE"),
    ("Hi\n\n<p>I said MicroLife was back in stock. It isn't -- still on order.</p>", True, None),
    ("Hi\n\n<p>Skunk Nectar is back in stock and Cali Pro Grow is in stock.</p>", False, "Skunk Nectar"),
    ("Hi\n\n<p>We just published a new guide on autumn tents, worth a read.</p>", False, "new guide"),
    ("Hi\n\n<p>SiLution is in stock at $68.00. BIG15 on Bionova, BIG10 on the rest.</p>", True, None),
    ("Hi\n\n<p>Nights are cold; check runoff pH before you change your feed. - Barry</p>", True, None),
]
bad = []
for text, ok, needle in CASES:
    r = factcheck.check_email(text)
    if r["ok"] != ok or (needle and not any(needle.lower() in p.lower() for p in r["problems"])):
        bad.append((text[:60], ok, r["ok"], r["problems"]))
for b in bad:
    print("FAIL", b)
if bad:
    raise SystemExit(1)
print(f"factcheck battery: ALL PASS ({len(CASES)} cases)")
