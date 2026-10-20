"""THE OFFICE CLOCK -- when the agents are on the clock, and when they are not.

Barry, 2026-09-01: "give them 6am to 6pm for work times. But they are on call",
then, the same conversation: "i ususally turn my pc on around 9 so lets make it
9 to 6" and "weekends off."

Barry, 2026-09-26: "no days off. they are bots" / "Til 6 pm" -- EVERY DAY.

Barry, 2026-09-27: "everyone else can chill on sundays unless i need something
done" / "i need Elliot [to] give me shots whenever i ask" -- Monday to
Saturday. Elliot needs no exemption: nothing here blocks Barry asking (below).

So: MONDAY TO SATURDAY, 9am to 6pm, is work. Everything else -- evenings and
nights -- is their own time. And they are ON CALL the whole time,
which in this build means exactly one thing: nothing in here ever blocks Barry.
He can open the green work channel at 3am on a Sunday and get a full work
answer. The clock governs what THEY do unprompted; it never governs what HE
can ask for.

WHY THIS IS ONE MODULE AND NOT AN `if` IN THREE FILES: the same lesson
`jobs.py` was built on. The moment two files each decide what "work hours"
means, they drift, and the drift is invisible until an agent writes Barry a
margin note at midnight and nobody can say which check let it through. One
definition, every caller asks it, every decision is loggable.

LIVE, NOT HARDCODED (his word: "live"). The hours sit in `app_settings`, so
moving them is one call and no restart -- same mechanism as
`dispatch_enabled`. The constants below are only the fallback for a brand-new
database. A corrupt or nonsense stored value degrades to the defaults rather
than raising, because a bad settings row must never be able to break a chat.

    memory.set_setting("work_hours_start", "8")     # open at 8am
    memory.set_setting("work_hours_end", "17")      # close at 5pm
    memory.set_setting("work_days", "0,1,2,3,4,5")  # add Saturday

⚠️ CACHE SAFETY -- READ THIS BEFORE PUTTING ANY OF IT IN A PROMPT.
`state()` is deliberately COARSE: on the clock or off, and a day-shaped word.
It must never carry the minute, because the presence block is part of the
system-prompt PREFIX, and llama-server only reuses an UNCHANGED prefix. A
minute-level clock in there is what caused the 61-second prefills on
2026-08-20 (every message re-read all 50K tokens). A value that flips twice a
day busts the cache twice a day, which is free. Keep it that way.
"""

import datetime

import memory

# Fallbacks for a fresh database. The live values live in app_settings.
DEFAULT_START_HOUR = 9        # 9am, when Barry usually turns the PC on
DEFAULT_END_HOUR = 18         # 6pm
DEFAULT_DAYS = (0, 1, 2, 3, 4, 5)  # Monday=0 ... Saturday=5. Sundays off (2026-09-27).

START_KEY = "work_hours_start"
END_KEY = "work_hours_end"
DAYS_KEY = "work_days"

_DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday",
              "Friday", "Saturday", "Sunday")


def _int_setting(key: str, fallback: int, lo: int, hi: int) -> int:
    """One stored hour, or the fallback if it is missing/junk/out of range."""
    try:
        val = int(str(memory.get_setting(key, "")).strip())
    except (TypeError, ValueError):
        return fallback
    return val if lo <= val <= hi else fallback


def hours() -> tuple[int, int, tuple[int, ...]]:
    """(start_hour, end_hour, work_days) as they stand RIGHT NOW.

    Read live on every call -- one indexed row each, the same cost the brain
    already pays per message -- so a change through set_setting() is in force
    on the very next message with no restart. That is the whole point of
    storing it here instead of in a constant.
    """
    start = _int_setting(START_KEY, DEFAULT_START_HOUR, 0, 23)
    end = _int_setting(END_KEY, DEFAULT_END_HOUR, 1, 24)
    if end <= start:                       # nonsense pair -> fall back whole
        start, end = DEFAULT_START_HOUR, DEFAULT_END_HOUR
    raw = memory.get_setting(DAYS_KEY, "")
    days = tuple(sorted({int(p) for p in str(raw).replace(" ", "").split(",")
                         if p.isdigit() and 0 <= int(p) <= 6})) or DEFAULT_DAYS
    return start, end, days


def is_work_hours(now: datetime.datetime | None = None) -> bool:
    """True when the office is open. The single question everything asks."""
    now = now or datetime.datetime.now()
    start, end, days = hours()
    return now.weekday() in days and start <= now.hour < end


def next_open(now: datetime.datetime | None = None) -> str:
    """Plain words for when the office opens again -- "at 9am", "Monday
    morning". Used to tell Barry when a held note will surface, and to tell
    an agent when the thing they wanted to raise will actually land. Never
    a timestamp: this ends up in prompts, see the cache note above."""
    now = now or datetime.datetime.now()
    start, _end, days = hours()
    if is_work_hours(now):
        return "now -- the office is open"
    hour_word = f"{start % 12 or 12}{'am' if start < 12 else 'pm'}"
    # Same day, before opening? Then it is simply this morning.
    if now.weekday() in days and now.hour < start:
        return f"at {hour_word} this morning"
    for ahead in range(1, 8):
        day = now + datetime.timedelta(days=ahead)
        if day.weekday() in days:
            when = "tomorrow" if ahead == 1 else _DAY_NAMES[day.weekday()]
            return f"{when} at {hour_word}"
    return f"at {hour_word}"                # no work days configured at all


def state(now: datetime.datetime | None = None) -> dict:
    """Everything a prompt is allowed to know about the clock.

    COARSE ON PURPOSE (see the cache warning at the top of this file):
    on_clock, the day name, and a sentence. No minutes, ever.
    """
    now = now or datetime.datetime.now()
    on = is_work_hours(now)
    start, end, _days = hours()
    span = (f"{start % 12 or 12}{'am' if start < 12 else 'pm'} to "
            f"{end % 12 or 12}{'am' if end < 12 else 'pm'}")
    # Days read from the live setting -- this line said "Monday to Friday"
    # long after the days changed (2026-09-27).
    ds = sorted(_days)
    if ds == list(range(ds[0], ds[-1] + 1)) and len(ds) > 1:
        dayspan = f"{_DAY_NAMES[ds[0]]} to {_DAY_NAMES[ds[-1]]}"
    else:
        dayspan = ", ".join(_DAY_NAMES[d] for d in ds)
    if on:
        line = (f"It is {_DAY_NAMES[now.weekday()]} and you are ON THE CLOCK. "
                f"Office hours are {span}, {dayspan}.")
    else:
        # ON CALL, ALWAYS (Barry, 2026-09-27: "they are on call, always, so if
        # i need office work done, they should do it" / "for important things
        # only").
        line = (f"It is {_DAY_NAMES[now.weekday()]} and you are OFF THE CLOCK "
                f"-- the office is closed. Office hours are {span}, {dayspan}. "
                f"You are ON CALL, always: Barry only brings work outside office "
                f"hours when it is important, so when he does, you do it now and "
                f"do it properly -- no waiting for the office to open, no friction "
                f"about the hour. Nothing he didn't ask for gets started on your "
                f"own until the office opens.")
    return {"on_clock": on, "day": _DAY_NAMES[now.weekday()],
            "span": span, "line": line, "next_open": next_open(now)}
