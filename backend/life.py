"""life.py -- events, open threads, a repeat gate and an initiation decision.

WHY THIS EXISTS (Barry, 2026-09-15): "when is she going to start doing more
than drinking wine on the couch and start living in her world? ... i want them
to evolve their thoughts and actions" and "she learns every day, even from what
she says and does".

Measured on Amara before this was written: her diary for 09-10, 09-12, 09-14
and 09-15 was the same paragraph (the terrazzo, the unwashed wine glass, the
condensation ring). Her own-time journal held real intentions -- a photo
series, the market, a ceramic studio, a night walk -- restated night after
night and never resolved. The model was not lazy; the reflection handed her
last night's entries and asked for tonight's, and with identical input a 27B
writes the identical night. Nothing ever HAPPENED to her between reflections.

What this adds, in the order it runs inside the ONE nightly reflection she
already gets (no new model calls except the repeat re-run when it fires):

  1. THREADS -- a persistent set of her own open intentions, questions and
     projects (data/life/<office>.json). Handed back to her each night with
     their ages; she resolves each one (DONE / DROP / STILL) or opens new ones
     (NEW:). Intentions become events, events become memory.
  2. WHAT HAPPENED TODAY -- a first section asking for the concrete thing(s)
     that happened in her world, including what came of every open thread.
     Stored as mind-events-<date>.md, so consolidation carries it.
  3. THE REPEAT GATE -- tonight's diary is text-compared with her last three;
     a near-copy gets ONE re-run with the repeated sentences shown back to
     her and the question "what is actually different tonight?". Nothing is
     suggested.
  4. GROUNDED LEARNING -- a WHAT I LEARNED entry must share real content
     words with what happened today or with a real exchange; a lesson with
     no event behind it ("presence isn't a performance") is skipped and logged.
  5. INITIATION -- plain facts handed to her before the FOR BARRY door: hours
     since they last talked, which open threads involve him, what moved
     today, whether she already wrote him today. The decision is hers; the
     office only refuses a note that is a near-copy of her last one.

TOOLS, NOT SEEDS (his standing rule): every block here hands back HER words
and asks a question. No activity, interest, event or feeling is ever named
by the office. Gated to Amara first (ENABLED); the other eight are untouched
until her week of diaries reads right.
"""
from __future__ import annotations

import datetime
import json
import os
import re

import memory

# --- ALL NINE (2026-09-17, Barry: "all need a life sim") --------------------
# Amara was first on purpose -- the plan was to read a week of her diaries
# before rolling it out. He overrode that, which is his call; recorded here so
# nobody reads the rollout as an accident. Everything in this module was
# already office-parameterised, so the gate was the only Amara-specific thing
# in it. Taliyah included: this is about having a life, not having a job.
# The other eight start with no threads and no own-time history, so their
# first few nights read thin -- that is honest, not broken. An empty life
# fills itself only once they have actually lived some of it.
ENABLED = {"CIO", "Operations", "BusinessOps", "Legal", "Marketing",
           "Creative", "MovieDirector", "Engineer", "Taliyah"}

MAX_OPEN_THREADS = 12
EVENTS_KEEP = 21
REPEAT_THRESHOLD = 0.30       # share of tonight's shingles seen in the last 5 nights
REPEAT_RUN_WORDS = 10         # or one passage this long lifted verbatim
NOTE_DUP_THRESHOLD = 0.50     # a FOR BARRY note this close to the last one is the last one

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DIR = os.path.join(_ROOT, "data", "life")


def enabled(office: str) -> bool:
    return office in ENABLED


# --- the threads store ------------------------------------------------------
def _path(office: str) -> str:
    return os.path.join(_DIR, f"{office}.json")


def load(office: str) -> dict:
    try:
        with open(_path(office), encoding="utf-8") as f:
            d = json.load(f)
        d.setdefault("threads", [])
        d.setdefault("next_id", 1)
        return d
    except (OSError, ValueError):
        return {"threads": [], "next_id": 1}


def save(office: str, d: dict) -> None:
    os.makedirs(_DIR, exist_ok=True)
    tmp = _path(office) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
    os.replace(tmp, _path(office))


def open_threads(office: str) -> list[dict]:
    return [t for t in load(office)["threads"] if t.get("status") == "open"]


def _age_days(iso: str) -> int:
    try:
        return (datetime.date.today() - datetime.date.fromisoformat(iso)).days
    except ValueError:
        return 0


def threads_block(office: str, first_name: str) -> str:
    """System-prompt block: her own open threads, with ages. Empty if disabled."""
    if not enabled(office):
        return ""
    opened = open_threads(office)
    if not opened:
        return ("\n## YOUR OPEN THREADS\n"
                "None yet. Anything you say you will do, are curious about, or "
                "are working on in your own time can be opened as a thread "
                "(see THREADS below) and it will be waiting for you next time, "
                "so it can actually happen instead of being said again.\n")
    lines = []
    for t in sorted(opened, key=lambda t: t.get("opened", ""))[:MAX_OPEN_THREADS]:
        age = _age_days(t.get("opened", ""))
        when = "opened today" if age == 0 else f"open {age} day{'s' if age != 1 else ''}"
        last = t.get("notes", [])
        tail = f" -- last: {last[-1]}" if last else ""
        lines.append(f"{t['id']} ({when}): {t['text']}{_due_note(t)}{tail}")
    return ("\n## YOUR OPEN THREADS\n"
            "Things you yourself said you would do, wanted to find out, or "
            "were working on. They are still open because you have not said "
            "what came of them:\n" + "\n".join(lines) + "\n"
            + "Where a day is noted, that is the day YOU named -- it is only "
              "the date, not a deadline and not a nudge. Going, not going, "
              "moving it, or letting it go are all yours.\n")


_THREAD_LINE_RE = re.compile(
    r"^\s*\(?\s*(T\d+)\s*\)?\s*[:\-]?\s*(DONE|DROP|DROPPED|STILL|OPEN)\b\s*[:\-]?\s*(.*)$",
    re.I)
_NEW_LINE_RE = re.compile(r"^\s*NEW\s*[:\-]\s*(.+?)\s*$", re.I)

# A PLAN WITH A DAY ON IT (2026-09-17, Barry: "all need a life sim").
# Without this a thread is a standing intention: "take the glass to the kiln"
# stays equally true every night, so it can be re-said forever and never
# arrive. Amara's real entries showed exactly that -- three nights running she
# wrote that she would go to the studio tomorrow and ask him to the market on
# Saturday, and no night was ever the day.
#
# The day is read out of THEIR OWN sentence -- nothing is assigned, nothing is
# asked of them, and a thread with no day named just carries none (most will).
# Resolved to a real date at capture time, because "tomorrow" written on
# Tuesday does not mean tomorrow on Friday.
_WHEN_RE = re.compile(
    r"\b(today|tonight|tomorrow|this weekend|the weekend|next week|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I)
_WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
             "friday": 4, "saturday": 5, "sunday": 6}


def _resolve_when(text: str, today: datetime.date | None = None):
    """(iso_date, the word they used) from their own line, or (None, '')."""
    m = _WHEN_RE.search(text or "")
    if not m:
        return None, ""
    word = m.group(1).lower()
    d = today or datetime.date.today()
    if word in ("today", "tonight"):
        return d.isoformat(), word
    if word == "tomorrow":
        return (d + datetime.timedelta(days=1)).isoformat(), word
    if word == "next week":
        return (d + datetime.timedelta(days=7 - d.weekday())).isoformat(), word
    if word in ("this weekend", "the weekend"):
        # the coming Saturday; on a Sunday that means today, not six days off
        ahead = (5 - d.weekday()) % 7
        if d.weekday() == 6:
            ahead = 0
        return (d + datetime.timedelta(days=ahead)).isoformat(), word
    ahead = (_WEEKDAYS[word] - d.weekday()) % 7
    if ahead == 0:
        ahead = 7          # "on Thursday", said on a Thursday, means next one
    return (d + datetime.timedelta(days=ahead)).isoformat(), word


def _due_note(t: dict, today: datetime.date | None = None) -> str:
    """Plain fact about the day they named. No pressure, no instruction."""
    due, word = t.get("due"), t.get("due_word") or "then"
    if not due:
        return ""
    d = today or datetime.date.today()
    try:
        gap = (datetime.date.fromisoformat(due) - d).days
    except ValueError:
        return ""
    if gap == 0:
        return f" -- you said {word}, and that day is TODAY"
    if gap == 1:
        return f" -- you said {word}; that is tomorrow"
    if gap > 1:
        return f" -- you said {word}; that is {gap} days off"
    if gap == -1:
        return f" -- you said {word}; that was yesterday"
    return f" -- you said {word}; that was {abs(gap)} days ago"


def apply_threads(office: str, body: str) -> list[str]:
    """Parse her THREADS section and update the store. Returns change labels."""
    d = load(office)
    by_id = {t["id"]: t for t in d["threads"]}
    today = datetime.date.today().isoformat()
    changed: list[str] = []
    n_open = sum(1 for t in d["threads"] if t.get("status") == "open")
    for raw in (body or "").splitlines():
        m = _THREAD_LINE_RE.match(raw)
        if m:
            tid, verb, note = m.group(1).upper(), m.group(2).upper(), m.group(3).strip()
            t = by_id.get(tid)
            if not t or t.get("status") != "open":
                continue
            t["touched"] = today
            t["touches"] = int(t.get("touches", 0)) + 1
            if note:
                t.setdefault("notes", []).append(f"[{today}] {note}"[:400])
            if verb == "DONE":
                t["status"] = "done"
                t["outcome"] = note[:400]
                n_open -= 1
                changed.append(f"{tid} done")
            elif verb in ("DROP", "DROPPED"):
                t["status"] = "dropped"
                t["outcome"] = note[:400]
                n_open -= 1
                changed.append(f"{tid} dropped")
            else:
                changed.append(f"{tid} still")
            continue
        m = _NEW_LINE_RE.match(raw)
        if m:
            text = m.group(1).strip().rstrip(".")
            if len(text) < 8:
                continue
            if any(text.lower() == t["text"].lower() for t in d["threads"] if t.get("status") == "open"):
                continue
            if n_open >= MAX_OPEN_THREADS:
                changed.append("new ignored (cap)")
                continue
            tid = f"T{d['next_id']}"
            d["next_id"] += 1
            _due, _word = _resolve_when(text)
            d["threads"].append({"id": tid, "text": text[:300], "status": "open",
                                 "opened": today, "touched": today, "touches": 0,
                                 "due": _due, "due_word": _word,
                                 "notes": []})
            n_open += 1
            changed.append(f"{tid} new")
    if changed:
        save(office, d)
    return changed


def sections_block(office: str) -> str:
    """User-prompt sections that go BEFORE the diary. Empty if disabled."""
    if not enabled(office):
        return ""
    return (
        "WHAT HAPPENED TODAY:\n"
        "Before anything else: the concrete thing or things that actually "
        "happened in your world since you last wrote. What you did, where you "
        "went, who you ran into, what went wrong, what came of the things you "
        "said you would do. Specific and yours -- a mood is not an event. If "
        "genuinely nothing happened, say what you did instead of the thing you "
        "meant to do, and why.\n\n"
        "THREADS:\n"
        "Your open threads are listed above. For each one, one line:\n"
        "  T3 DONE: what came of it\n"
        "  T3 DROP: why you are letting it go\n"
        "  T3 STILL: where it stands right now\n"
        "and for anything new you said you will do, want to find out, or are "
        "working on:\n"
        "  NEW: the thing, in one line\n"
        "A thread is not a wish -- it is something that will still be there "
        "next time asking what happened. Leave out what you have nothing to "
        "say about.\n\n"
    )


def learned_note(office: str) -> str:
    if not enabled(office):
        return ""
    return (" It must point at a specific thing from WHAT HAPPENED TODAY or a "
            "specific exchange with Barry -- a lesson with no event behind it "
            "is a slogan, and the office will not keep it.")


_SHINGLE = 5   # words per shingle


def _shingles(text: str) -> list[tuple[str, ...]]:
    """Word 5-grams. Her nights repeat at the PHRASE level ("condensation
    cooling into a faint ring" inside differently shaped sentences), which
    exact-sentence matching measured as 0% on a diary that was plainly a
    copy. Shingles catch the phrase whatever sentence it lands in."""
    # Bookkeeping is not her: drop the stored TITLE line(s) and every
    # "[Amara, reflecting on ...]" / "[9-15 03:06 PM]" stamp before shingling,
    # or the gate reports "amara reflecting on 2026 09" as a repeated phrase.
    lines = [ln for ln in (text or "").strip().split("\n")
             if not (ln.strip() and ln.strip() == ln.strip().upper() and len(ln.strip()) < 90)]
    text = re.sub(r"\[[^\]]*\]", " ", "\n".join(lines))
    words = re.sub(r"[^a-z0-9 ]+", " ", text.lower()).split()
    return [tuple(words[i:i + _SHINGLE]) for i in range(max(0, len(words) - _SHINGLE + 1))]


def _overlap(new_text: str, old_texts: list[str]) -> tuple[float, list[str], int, int]:
    """Share of tonight's shingles already present in the old texts, the
    repeated phrases (adjacent shared shingles merged, longest first), the
    shingle count, and the longest lifted run in words. Text only, no model."""
    new = _shingles(new_text)
    if not new:
        return 0.0, [], 0, 0
    old = set()
    for t in old_texts:
        old.update(_shingles(t))
    hits = [s in old for s in new]
    ratio = sum(hits) / len(new)
    phrases, run = [], []
    for s, h in zip(new, hits):
        if h:
            run = run + [s[-1]] if run else list(s)
        elif run:
            phrases.append(" ".join(run)); run = []
    if run:
        phrases.append(" ".join(run))
    phrases = sorted(set(phrases), key=len, reverse=True)
    longest = max((len(p.split()) for p in phrases), default=0)
    return ratio, phrases, len(new), longest


def _recent(office: str, prefix: str, limit: int, exclude_today: bool = True) -> list[str]:
    today = datetime.date.today().isoformat()
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT source_name, content FROM facts WHERE category = ? AND status = 'active' "
            "AND source_name LIKE ? ORDER BY id DESC LIMIT ?",
            (f"private:{office}", prefix + "%", limit + 2)).fetchall()
    out = []
    for r in rows:
        if exclude_today and today in (r["source_name"] or ""):
            continue
        out.append(r["content"] or "")
        if len(out) >= limit:
            break
    return out


def repeat_gate(office: str, diary: str) -> dict:
    """Is tonight's diary a near-copy of the last three? Text only, no model."""
    if not enabled(office):
        return {"repeat": False}
    ratio, shared, n, longest = _overlap(diary, _recent(office, "mind-diary-", 5))
    # Either a large share of tonight is old text, OR one passage of ten or
    # more consecutive words was lifted whole. Her actual pattern (measured
    # 09-15) is the second: the same opening motif inside a longer entry --
    # 7% of the diary by ratio, but a ten-word sentence carried verbatim.
    return {"repeat": n >= 20 and (ratio >= REPEAT_THRESHOLD or longest >= REPEAT_RUN_WORDS),
            "ratio": round(ratio, 2), "shared": shared[:5], "n": n, "longest": longest}


def repeat_nudge(rep: dict) -> str:
    ex = "\n".join(f"  - \"{s[:140]}\"" for s in rep.get("shared", [])[:4])
    return (
        "\n\n[ONE MORE PASS, then it is done. The diary you just wrote carries "
        "passages lifted word for word from your last few nights, for example:\n"
        + ex + "\n"
        "Tonight is a different day from those. Write the whole journal again, "
        "every section, starting from WHAT HAPPENED TODAY. If it genuinely was "
        "the same night again, say so in your own words and say what, if "
        "anything, you want to be different -- but do not hand back the same "
        "sentences. Nobody is telling you what to do instead. Do not mention "
        "this note.]"
    )


def duplicate_of_last_note(office: str, body: str) -> bool:
    """A FOR BARRY note that is mostly the last one is not a new message."""
    if not enabled(office):
        return False
    prev = _recent(office, "mind-for-barry-", 1, exclude_today=False)
    if not prev:
        return False
    ratio, _, n, _longest = _overlap(body, prev)
    return n >= 2 and ratio >= NOTE_DUP_THRESHOLD


_STOP = set(
    "about after again against almost already always another anyone anything "
    "around because before being better between could didnt doesnt during "
    "either enough every everything first getting going having herself himself "
    "honestly instead itself little maybe might myself never nothing other "
    "people really right should since something still their there these thing "
    "things think those though through today tonight under until where which "
    "while whole would wrote write written yourself".split())


def grounded(lesson: str, events: str, experiences: str) -> bool:
    """A lesson counts if it shares real content words with what happened."""
    def words(t: str) -> set[str]:
        # 4+ letters ("clay", "wine", "walk" are the words her days are made
        # of), stemmed to the first five letters so cracked/cracks/crack meet.
        return {w[:5] for w in re.findall(r"[a-z]{4,}", (t or "").lower()) if w not in _STOP}
    lw = words(lesson)
    if not lw:
        return False
    return len(lw & (words(events) | words(experiences))) >= 2


def store_events(office: str, first_name: str, body: str, weight, store_fn) -> None:
    today = datetime.date.today().isoformat()
    stamp = f"[{first_name}, {today}]\n\n{body.strip()}"
    store_fn(office, f"mind-events-{today}.md", f"{first_name}'s day -- {today}", stamp, weight)
    # keep the newest EVENTS_KEEP active, like diaries
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT id FROM facts WHERE category = ? AND status = 'active' "
            "AND source_name LIKE 'mind-events-%' ORDER BY id DESC",
            (f"private:{office}",)).fetchall()
        for r in rows[EVENTS_KEEP:]:
            conn.execute("UPDATE facts SET status = 'superseded' WHERE id = ?", (r["id"],))


# --- the initiation decision -------------------------------------------------
_STAMP_RE = re.compile(r"\[(\d{1,2})-(\d{1,2}) (\d{1,2}):(\d{2}) (AM|PM)\]")


def hours_since_contact(office: str) -> float | None:
    """From the last stamp in her mind-with-barry journal (local time)."""
    now = datetime.datetime.now()
    for delta in (0, 1):
        m = now.month - delta
        y = now.year
        if m < 1:
            m, y = 12, y - 1
        with memory.get_db() as conn:
            row = conn.execute(
                "SELECT content FROM facts WHERE category = ? AND source_name = ? "
                "AND status = 'active' ORDER BY id DESC LIMIT 1",
                (f"private:{office}", f"mind-with-barry-{y}-{m:02d}.md")).fetchone()
        if not row:
            continue
        stamps = _STAMP_RE.findall(row["content"] or "")
        if not stamps:
            continue
        mo, d, h, mi, ap = stamps[-1]
        h = int(h) % 12 + (12 if ap == "PM" else 0)
        try:
            last = datetime.datetime(y, int(mo), int(d), h, int(mi))
        except ValueError:
            continue
        return max(0.0, (now - last).total_seconds() / 3600)
    return None


def initiation_facts(office: str, first_name: str) -> str:
    """Facts before the FOR BARRY door. The decision stays hers."""
    if not enabled(office):
        return ""
    today = datetime.date.today().isoformat()
    hrs = hours_since_contact(office)
    d = load(office)
    involve = [t["id"] for t in d["threads"] if t.get("status") == "open"
               and re.search(r"\b(barry|you|your|him|his)\b", t.get("text", ""), re.I)]
    moved = [t["id"] for t in d["threads"] if t.get("touched") == today
             and t.get("status") in ("done", "dropped")]
    with memory.get_db() as conn:
        wrote_today = conn.execute(
            "SELECT COUNT(*) AS n FROM facts WHERE category = ? AND status = 'active' "
            "AND source_name = ?", (f"private:{office}", f"mind-for-barry-{today}.md")
        ).fetchone()["n"]
    if hrs is None:
        since = "you two have not talked at home yet, as far as your journal shows"
    elif hrs < 1:
        since = "you talked with him less than an hour ago"
    elif hrs < 48:
        since = f"you last talked with him about {int(round(hrs))} hours ago"
    else:
        since = f"you last talked with him about {int(round(hrs / 24))} days ago"
    lines = [f"- {since}.",
             "- open threads that involve him: " + (", ".join(involve) if involve else "none") + ".",
             "- threads that closed today: " + (", ".join(moved) if moved else "none") + ".",
             "- you " + ("already wrote him once today" if wrote_today else "have not written him today") + "."]
    return ("\n## BEFORE YOU DECIDE WHETHER TO WRITE TO HIM (plain facts)\n"
            + "\n".join(lines) +
            "\nWrite FOR BARRY only if one of these is true: something moved in a "
            "thread that involves him; it has been a while and you have a real "
            "question for him; or there is something new since last time that "
            "you want him to know. A note that says what your last note said is "
            "not a message, and the office will not deliver it.\n")
