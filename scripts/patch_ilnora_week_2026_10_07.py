"""One-off patch (2026-10-07): Ilnora's new week -- Sunday planning (next 5 videos, incl. one redo), 2-3 Shorts every
night after hours, Saturday Long, the redo docket + the redo exemption in video_tool's no-remake check."""
import os
import shutil

B = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
DATA = os.path.join(os.path.dirname(B), "data")

t = ""


def rep(a, b):
    global t
    assert t.count(a) == 1, a[:70]
    t = t.replace(a, b)


p = os.path.join(B, "video_queue.py")
shutil.copy(p, os.path.join(DATA, "backup_video_queue_before_week_2026-10-07.py"))
t = open(p, encoding="utf-8").read()

rep('''SCHEDULE (her writing turns, through her own seat like Derek's email jobs -- the office tells her what is due and
hands her her own plan; the topics, words and shots are hers):
    Saturday 11:00  plan next week: the Shorts and 2 Longs (topic, hook, her look) -> data/video_queue/plan.md
    every day 15:00  half of "3 shorts 1 long" every 2 days, alternating: 2 Shorts / 1 Short + 1 Long
    "video_shorts_per_day" (live setting, default 3) is the daily count; a backlog of 3+ unbuilt Shorts makes it 2,
    6+ skips the day -- the card can't keep up, so she doesn't write into a pile.''',
'''SCHEDULE (2026-10-07, Barry: "sunday was her planning day. she plans out the next 5 videos. i want to generate after
hours every day" / "she can make a video or 2 sunday as well after planning" / "2-3 still a day" / deep dives weekly /
the redos: "add 1 of those videos in a week, not only do those. just add it in"). Her writing turns go through her
own seat; the office tells her what is due and hands her her own plan -- the topics, words and shots are hers:
    Sunday 18:00     plan her next 5 videos (one is that week's REDO from data/video_queue/redo/docket.json),
                     then 1-2 Shorts
    Mon-Fri 18:00    2-3 Shorts (card budget below); when 5 videos have been made since the plan, she plans the next 5
    Saturday 18:00   the week's Long (deep dive) -- a Long night has no room for Shorts
    "video_shorts_per_day" (live setting) caps a night; a backlog of 3+ unbuilt Shorts makes it 2, 6+ skips the night.''')

rep('''SHORTS_BUDGET_MIN = 240                # card minutes for a 2-Shorts day (two full Shorts, or up to 5 teasers)
SHORTS_BUDGET_LONG_DAY = 120           # the Long's day: one full Short's worth beside the Long
MAX_SHORTS_PER_DAY = 5                 # Barry: "maybe 5"''',
'''SHORTS_BUDGET_NIGHT = 480             # estimated card minutes, Mon-Fri: 2-3 full Shorts (estimates run 1.1-1.7x short)
SHORTS_BUDGET_SUNDAY = 240            # Sunday after planning: 1-2 Shorts
MAX_SHORTS_PER_DAY = 3                 # Barry: "2-3 still a day"
LONG_NIGHT = 5                         # Saturday: the week's deep dive
PLAN_SIZE = 5                          # Barry: "she plans out the next 5 videos"
REDO_DIR = os.path.join(QDIR, "redo")
DOCKET = os.path.join(REDO_DIR, "docket.json")''')

rep('''# (weekday Mon=0, hour, what)
# no Sunday writing slot: Sunday the card is busy with her own builds and her writing turn needs Bonsai, so
# Saturday's batch writes ALL of Sunday's videos
# Barry 2026-10-04: "i only want her to create the 4 videos every 2 days. The rest of the office needs to be able to
# work too" -> "3 shorts 1 long". Every day at 15:00 she writes half of it, alternating by date: day A = 2 Shorts
# (~4 h of building that night), day B = 1 Short + 1 Long (~13 h, fits 18:00-09:00). Saturday 11:00 = planning.
SLOTS = [(5, 11, "plan")] + [(d, 15, "daily") for d in range(7)]''',
'''# (weekday Mon=0, hour, what) -- all after hours (18:00), so the rest of the office keeps Bonsai all day; the plan
# runs before Sunday's videos (same tick, SLOTS order)
SLOTS = [(6, 18, "plan")] + [(d, 18, "daily") for d in range(7)]''')

rep('''async def plan_week() -> None:
    made = _recent_made()
    msg = ("Scheduled job from the office: it's Saturday, your planning day. Plan next week's videos: a Short for "
           "each slot (2 a day, Sunday through Friday) and 2 Long videos (10 minutes or more each). For each one: "
           "the topic, the hook you open with, the angle that makes it yours, and your look for your own parts "
           "(what you wear, where you are). Write the plan in your reply -- the office keeps it and hands it back "
           "to you each time you make a video this week."''',
'''# ------------------------------------------------------------------ redos (2026-10-07)
# Barry: "delete them but I want them redone at some point" / "she redo 1 a week" / "let her redo the names, but tell
# her these are redos". One redo goes into each plan, in docket order; while it is open its plants are let through
# the no-remake check (video_tool.check) -- they are in posted videos -- and it closes when a video with them queues.
def _docket() -> list[dict]:
    try:
        return json.load(open(DOCKET, encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save_docket(d: list[dict]) -> None:
    with open(DOCKET, "w", encoding="utf-8") as fh:
        json.dump(d, fh, indent=1, ensure_ascii=False)


def active_redo() -> dict | None:
    return next((r for r in _docket() if r.get("assigned") and not r.get("done")), None)


def redo_plant_keys() -> set:
    import video_tool
    r = active_redo()
    return {video_tool._plant_key(p) for p in (r or {}).get("plants", [])}


def _assign_redo() -> dict | None:
    d = _docket()
    open_one = next((r for r in d if r.get("assigned") and not r.get("done")), None)
    if open_one:
        return open_one
    week = datetime.date.today().isocalendar()[:2]
    if any(r.get("assigned") and tuple(datetime.date.fromisoformat(r["assigned"]).isocalendar()[:2]) == week
           for r in d):
        return None                                          # this week's redo is already done
    nxt = next((r for r in d if not r.get("assigned")), None)
    if nxt:
        nxt["assigned"] = datetime.date.today().isoformat()
        _save_docket(d)
        _log(f"redo assigned: {nxt['title']}")
    return nxt


def _close_redo(pkg: dict) -> None:
    import video_tool
    d = _docket()
    r = next((x for x in d if x.get("assigned") and not x.get("done")), None)
    if not r:
        return
    keys = {video_tool._plant_key(p) for p in r.get("plants", [])}
    if keys & {video_tool._plant_key(s.get("plant")) for s in pkg.get("scenes") or [] if s.get("plant")}:
        r["done"] = datetime.date.today().isoformat()
        r["new_title"] = pkg.get("title", "")
        _save_docket(d)
        _log(f"redo done: {r['title']} -> '{r['new_title']}'")


def _plan_needs_refresh() -> bool:
    """No plan yet, or 5 videos made since she planned (Barry: "she plans out the next 5 videos")."""
    at = _state().get("plan_at")
    if not at or not os.path.isfile(PLAN):
        return True
    return sum(1 for j in _jobs() if j.get("created", "") >= at) >= PLAN_SIZE


async def plan_week() -> None:
    made = _recent_made()
    redo = _assign_redo()
    msg = ("Scheduled job from the office: plan your next 5 videos. Before you pick, check channel_stats for what is "
           "posted and what people are watching, and list_files for every video you have made; then pick each one "
           "with the steps in your make-video-masterfully skill. For each one: the plant(s), the topic, the hook you "
           "open with, the angle that makes it yours, and your look for your own parts (what you wear, where you "
           "are). This week's Long (10 minutes or more) is made on Saturday night. Write the plan in your reply -- "
           "the office keeps it and hands it back to you each time you make a video."
           + (f'\\n\\nONE OF THE 5 IS A REDO: "{redo["title"]}" (plants: {", ".join(redo["plants"])}; '
              f'{"a Long" if redo.get("format") == "long" else "a Short"}). Barry: "these are redos. you redo the '
              f'names."' if redo else "")''')

rep('''        fh.write(reply + "\\n")
    _log(f"plan: saved ({len(reply)} chars)")''',
'''        fh.write(reply + "\\n")
    st = _state()
    st["plan_at"] = datetime.datetime.now().isoformat()
    _save_state(st)
    _log(f"plan: saved ({len(reply)} chars)")''')

rep('''    label = {"plan": "Saturday planning", "daily": "today's videos"}[what]
    if what == "plan":
        await plan_week()
        return''',
'''    label = {"plan": "Sunday planning", "daily": "tonight's videos"}[what]
    if what == "plan":
        await plan_week()
        return
    if _plan_needs_refresh():
        await plan_week()                                    # her 5 are used up (or there is no plan yet)
    wd = datetime.date.today().weekday()''')

rep('''    long_day = datetime.date.today().toordinal() % 2 == 1          # day B: Long + 1 Short's worth; day A: 2 Shorts'
    if long_day and not any(j["pkg"].get("format") == "long" for j in done_since):
        ok = await make_one("long", f"{label}, the Long")
        _log(f"{label}: long {'queued' if ok else 'missed'}")''',
'''    if wd == LONG_NIGHT:
        if not any(j["pkg"].get("format") == "long" for j in done_since):
            ok = await make_one("long", f"{label}, the week's Long")
            _log(f"{label}: long {'queued' if ok else 'missed'}")
        return                                               # a Long night has no room for Shorts''')

rep('''    budget = (SHORTS_BUDGET_LONG_DAY if long_day else SHORTS_BUDGET_MIN) if shorts_today() else 0''',
'''    budget = (SHORTS_BUDGET_SUNDAY if wd == 6 else SHORTS_BUDGET_NIGHT) if shorts_today() else 0
    max_n = min(2 if wd == 6 else MAX_SHORTS_PER_DAY, shorts_today())''')

rep('''    while used < budget - 45 and n < MAX_SHORTS_PER_DAY and misses < 2:''',
'''    while used < budget - 45 and n < max_n and misses < 2:''')

rep('''    ahead = len(queued()) - 1
    _log(f"queued '{pkg.get('title')}' ({pkg.get('format')}, ~{job['estimate_min']} min of card) -- {ahead} ahead")''',
'''    ahead = len(queued()) - 1
    _log(f"queued '{pkg.get('title')}' ({pkg.get('format')}, ~{job['estimate_min']} min of card) -- {ahead} ahead")
    try:
        _close_redo(pkg)
    except Exception as exc:  # noqa: BLE001 -- a docket hiccup never costs a queued video
        _log(f"redo docket: {type(exc).__name__}: {exc}")''')

open(p, "w", encoding="utf-8").write(t)
print("video_queue ok")

p2 = os.path.join(B, "video_tool.py")
shutil.copy(p2, os.path.join(DATA, "backup_video_tool_before_redo_2026-10-07.py"))
t = open(p2, encoding="utf-8").read()
rep('''    new_plants = {_plant_key(s.get("plant")): str(s.get("plant")) for s in scenes if s.get("plant")}''',
'''    new_plants = {_plant_key(s.get("plant")): str(s.get("plant")) for s in scenes if s.get("plant")}
    # THE WEEK'S REDO (2026-10-07, Barry: "she redo 1 a week"): the open redo's plants are in posted videos -- let
    # them through for it (video_queue.redo_plant_keys; closes when a video with them queues)
    redo_keys = video_queue.redo_plant_keys()''')
rep('''        used = sorted(new_plants[k] for k in new_plants if k in old_keys)''',
'''        used = sorted(new_plants[k] for k in new_plants if k in old_keys and k not in redo_keys)''')
open(p2, "w", encoding="utf-8").write(t)
print("video_tool ok")
