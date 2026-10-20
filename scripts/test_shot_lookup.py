"""Shot reference parsing + script lookup -- regression battery.

Run after ANY change to jobs.parse_shot_list, jobs._SHOT_TOK, or
script_index.read_scene's matching. This path produced silent wrong-block
bugs in three separate sessions ("Shots 2 and 3" dropping the 3, 08-23;
"shots 4-6" dropping the 5, and "shot 3" serving SHOT 01 off a LENS SPEC
substring, 08-25) and each survived because nothing could exercise the
logic without a live chat call. Companion to scripts/test_job_routing.py,
which covers ROUTING -- this covers what happens after the route fires.

Usage:  ../venv/Scripts/python.exe scripts/test_shot_lookup.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import jobs           # noqa: E402
import script_index   # noqa: E402

failures = []


def check(label, got, want):
    ok = got == want
    if not ok:
        failures.append(label)
    print(("OK  " if ok else "FAIL"), label, "->", got,
          ("" if ok else f"   (wanted {want})"))


# ---- parse_shot_list: lists, ranges, glued numbers, the letter traps ----
P = jobs.parse_shot_list
check("range 4-6", P("I think shots 4-6 with B roll added?"),
      [("SHOT", "4"), ("SHOT", "5"), ("SHOT", "6")])
check("range 4 through 6", P("give me shots 4 through 6"),
      [("SHOT", "4"), ("SHOT", "5"), ("SHOT", "6")])
check("list 2 and 3 (the 08-23 ghost)", P("Shots 2 and 3, please"),
      [("SHOT", "2"), ("SHOT", "3")])
check("glued shot5", P("you skipped shot5"), [("SHOT", "5")])
check("range then broll (letter trap)", P("shots 1 to 3 and b-roll 2"),
      [("SHOT", "1"), ("SHOT", "2"), ("SHOT", "3"), ("B-ROLL", "2")])
check("scene letter", P("scene c please"), [("SCENE", "C")])
check("scene letter list", P("scenes b and c"),
      [("SCENE", "B"), ("SCENE", "C")])
check("backwards range stays a list", P("shots 3-1 backwards"),
      [("SHOT", "3"), ("SHOT", "1")])
check("huge range NOT expanded (span>8)", P("shots 1-20"),
      [("SHOT", "1"), ("SHOT", "20")])
check("no shots at all", P("how does bia feel about keth?"), [])

# ---- read_scene: zero-pad canon, honest misses, no lens-spec matches ----
OFFICE = "MovieDirector"


def scene(q, expect_label=None, expect_miss=False):
    r = script_index.read_scene(OFFICE, q)
    if expect_miss:
        ok = (not r.get("found")) and "outline" in r
        if not ok:
            failures.append(f"read_scene {q!r}")
        print(("OK  " if ok else "FAIL"), f"read_scene {q!r}",
              "-> honest miss" if ok else f"-> {r.get('matched')}")
    else:
        m = r.get("matched") or []
        ok = r.get("found") and expect_label in m
        if not ok:
            failures.append(f"read_scene {q!r}")
        print(("OK  " if ok else "FAIL"), f"read_scene {q!r}", "->", m)


# V9A.1 (2026-09-07) carries Betty's ACT ZERO as plain SHOT 00-05 and V9's
# shots as 01A-23A. A bare number means the shot as it reads on the page:
# the plain label when one exists, else the lettered twin. An explicit
# letter resolves exactly as typed. (2026-09-14: Barry works from the top;
# "shot 1" must be Act Zero's SHOT 01, not THE RUN.)
scene("Shot 3", "SHOT 03")          # the 08-25 bug: served SHOT 01
scene("shot 5", "SHOT 05")          # the 08-25 bug: served SHOT 06
scene("SHOT 03", "SHOT 03")
scene("shot 1", "SHOT 01")          # the 09-14 bug: served SHOT 01A (THE RUN)
# V10 (live since 2026-09-21) has plain SHOT 00-28 and NO lettered twins, so
# the V9A.1 cases (01A, 09A) became stale, not broken. Updated 2026-09-23.
scene("shot 9", "SHOT 09")
scene("shot 28", "SHOT 28")
scene("shot 1a", expect_miss=True)  # no lettered blocks in V10 -> honest miss
scene("shot 0", "SHOT 00")
scene("b-roll 1", "B-ROLL 01")
scene("shot 99", expect_miss=True)  # honest miss + outline, never a guess
r = script_index.read_scene(OFFICE, "act two")
ok = r.get("found")
print(("OK  " if ok else "FAIL"), "read_scene 'act two' (section match)")
if not ok:
    failures.append("act two")
r = script_index.read_scene(OFFICE, "the run")
ok = r.get("found")
print(("OK  " if ok else "FAIL"), "read_scene 'the run' (title words) ->",
      r.get("matched"))
if not ok:
    failures.append("the run")

print()
if failures:
    print(f"FAILURES: {failures}")
    sys.exit(1)
print(f"ALL PASS")
