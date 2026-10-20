"""TEAMWORK -- briefs that actually get worked (2026-09-02).

Barry: "i need all this to work like a real company. All of them needs to be
able to work together if needed and Priya needs to really delegate and victor
needs to actually use her as an assistant."

WHAT WAS TRUE BEFORE, measured: delegate_to wrote a brief into the target's
brain as an always-on note and stopped. Nobody acted on it until Barry
happened to open that agent; no reply ever came back to whoever sent it; only
Victor and Priya could delegate at all; in the entire record exactly ONE brief
had ever been filed (Priya -> Victor, a test). Victor told me Priya "never runs
a specialist task herself", and Priya told me Victor and Barry are the same
person. Knowledge of the roles existed; the company did not.

WHAT THIS IS:
  A `briefs` table (the company's task board) and a worker loop that RUNS
  each brief through the target seat -- full persona, brain, tools, via
  /api/chat with `task: true` (the email-cadence pattern: nothing lands in
  their thread) -- and files the REPLY back to whoever asked. Delegation
  during a brief becomes a SUB-BRIEF (parent_id); the parent goes `waiting`,
  and when every child has reported the parent's seat is brought back once
  to COMPILE and close the loop. That is how Priya really delegates and how
  Victor really uses her: he hands her the coordination, she fans it out, the
  specialists report to her, she reports to him.

  Each seat's live position on the board rides in its prompt as ONE
  always-on fact (`team-loops`, regenerated, capped) -- briefs they hold and
  briefs they sent with the reply once it exists. `team_status` is the tool
  view; `chase_brief` re-queues something stale with a chaser note.

GUARDS: one brief per wake; never while Barry is mid-chat (a short idle gate,
not ideation's 10-minute one -- a company that only works after ten quiet
minutes is not working); a brief runs at most twice (initial + compile);
parent chains cap at depth 3; failures are recorded on the row, never
raised; anything outbound still goes through the approval queue exactly as
it does in live chat. Nothing here sends, posts or spends.
"""
import asyncio
import contextvars
import datetime
import os
import time

import httpx

import agent_files
import memory

_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_LOG = os.path.join(_DATA, "teamwork.log")

CHECK_INTERVAL_SECONDS = 60
STARTUP_DELAY_SECONDS = 120
IDLE_SECONDS = 90              # quiet for this long before a brief is worked
MAX_RUNS_PER_BRIEF = 3         # initial (+ one re-do if they answered for teammates) + compile
MAX_DEPTH = 3
LEDGER_SOURCE = "team-loops"   # no .md -> always-on, deliberately
LEDGER_CAP = 3000
DONE_VISIBLE_DAYS = 3

# The brief being worked in THIS request (set by main.py from ChatRequest.brief_id)
# so a delegate_to inside it becomes a sub-brief instead of a stray one.
current_brief_id: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "current_brief_id", default=None)

# TASKS ONLY WHEN BARRY CONFIRMS (2026-09-26, his hard rule: "tasks are only created when I
# confirm"). True only for a live /api/chat turn from Barry himself (main.py: not req.task). His own
# ask IS his confirmation, and a brief worked FROM his ask (current_brief_id) carries it on. A task
# an agent starts on its own -- ideation, nightly/learning reviews, email cadence, councils, social --
# is filed `proposed`: it never runs until he approves the `task_confirm` card. Code, not Laya.
barry_turn: contextvars.ContextVar[bool] = contextvars.ContextVar("barry_turn", default=False)


def confirmed_origin() -> bool:
    return bool(barry_turn.get()) or current_brief_id.get() is not None

_FIRST_NAMES = {"CIO": "Victor", "Operations": "Priya", "BusinessOps": "Amara",
                "Legal": "Marcus", "Marketing": "Derek", "Creative": "Vivian",
                "MovieDirector": "Elliot", "Engineer": "Sophie", "Taliyah": "Taliyah",
                "ilnora": "Ilnora"}   # 2026-10-10: all ten on the board
_ROLES = {"CIO": "CEO", "Operations": "Executive Assistant", "BusinessOps": "Business Operations",
          "Legal": "Legal Counsel", "Marketing": "Marketing", "Creative": "Creative Director",
          "MovieDirector": "Movie Director", "Engineer": "Engineer",
          "Taliyah": "Barry's companion", "ilnora": "Holistic Healer and video maker"}


def _log(msg: str) -> None:
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(f"[teamwork] {msg}")
    try:
        with open(_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


_BOOT = _now()   # when this process started -- recover_stale(startup=True)'s cutoff


def _dead_domains(text: str) -> list[str]:
    """Supplier domains named in a reply that do not resolve in DNS -- the
    cheapest possible "does this company exist" check (2026-09-11). Catches an
    invented supplier outright; it CANNOT judge a parked or unrelated domain,
    so a resolving name is not proof of a real supplier -- Barry's eyes are.
    Skipped under Offline Mode (a DNS lookup is a network action). Never raises."""
    import re as _re
    import socket
    try:
        if memory.is_offline_mode():
            return []
    except Exception:  # noqa: BLE001
        return []
    seen, dead = set(), []
    for d in _re.findall(r"\b((?:[a-z0-9-]+\.)+(?:com|net|org|co|io|shop|store|us|uk|de|it|eu))\b", (text or "").lower()):
        d = d.strip(".")
        if d in seen or d.count(".") > 3:
            continue
        seen.add(d)
        try:
            socket.getaddrinfo(d, 443)
        except Exception:  # noqa: BLE001 -- no address = does not exist
            dead.append(d)
    return dead


def ensure_schema() -> None:
    with memory.get_db() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS briefs ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " from_office TEXT NOT NULL, to_office TEXT NOT NULL,"
            " brief TEXT NOT NULL,"
            " status TEXT DEFAULT 'open',"          # open | working | waiting | done | failed
            " parent_id INTEGER,"
            " created_at TEXT NOT NULL, started_at TEXT, done_at TEXT,"
            " reply TEXT DEFAULT '', runs INTEGER DEFAULT 0,"
            " chaser TEXT DEFAULT '')")
        try:
            conn.execute("ALTER TABLE briefs ADD COLUMN huddle TEXT DEFAULT ''")
        except Exception:  # noqa: BLE001 -- column already there
            pass
        # ON CALL (2026-09-11, Barry: "the office is the on call part of their
        # lives... where i can give them stuff when not on the clock for them
        # to work on the next day"). A brief filed after hours carries the
        # UTC time the office next opens; _pick leaves it alone until then.
        try:
            conn.execute("ALTER TABLE briefs ADD COLUMN not_before TEXT DEFAULT ''")
        except Exception:  # noqa: BLE001 -- column already there
            pass


ensure_schema()


# --- THE HUDDLE: Victor and Priya go over it first --------------------------------
# Barry, 2026-09-02: "Victor and Priya talk about what i told him, they go over
# it then Priyah hands off." So a top-level brief from the CEO to his assistant
# does not just land on her board -- the two of them TALK IT THROUGH first, in
# work mode (their real seats, tools off), a few short turns: what Barry wants,
# the priorities, who should own what, what done looks like. The transcript is
# kept on the brief and handed to Priya as the plan she then hands off from.
# 3, not 4: measured 17 minutes for four turns -- every turn alternates two
# different ~28K-token prompts, so the Bonsai prompt cache misses each time.
# Victor opens, Priya asks, Victor answers; Priya's own brief run (which gets
# the transcript) is where she says the plan back and hands off.
HUDDLE_TURNS = 3


async def _huddle(b: dict) -> str:
    import llm_router
    import ingest
    import agents as _agents
    v = _agents.AGENTS["cio"]
    p = _agents.AGENTS["operations"]

    # THE BUSINESS CHAT (Barry, 2026-09-02: "if it saves gpu time, the brief and
    # huddle can be through a business chat or something, but only if it
    # helps"). It helps: a huddle turn used to carry each seat's full ~28K-token
    # work prompt and the two alternate, so the prompt cache missed every turn
    # (17 min for 4 turns). A huddle needs who they are, how the company works,
    # the Business Brain for real numbers, and the brief -- ~8K tokens.
    def _sys(agent: dict, other: str) -> str:
        me = agent["office_name"]
        brain = ""
        try:
            with memory.get_db() as conn:
                row = conn.execute(
                    "SELECT content FROM facts WHERE source_name='business-brain' AND "
                    "status='active' ORDER BY id DESC LIMIT 1").fetchone()
                brain = (row["content"] if row else "")[:7000]
        except Exception:
            pass
        role_block = _agents._VICTOR_RUNS_IT if me == "CIO" else _agents._PRIYA_DELEGATES
        s = (f"You are {name_of(me)}, {_ROLES.get(me, me)} at the company Barry White owns "
             "(B Dubb Grows LLC and Gotcho Back). This is a WORK conversation with your "
             f"colleague {other}. Talk like a real person who does this job, plainly, no "
             "corporate filler, no bullet lists, no headings."
             + _agents._WORKS_WITH_THE_TEAM + role_block
             + (f"\n\n## THE BUSINESS BRAIN (the facts you both work from)\n{brain}" if brain else ""))
        return s + (
            f"\n\n## GOING OVER BARRY'S ASK WITH {other.upper()}\n"
            "This is a working conversation between the two of you, on the clock, "
            "before anything is handed off. Talk like two people who work together "
            "every day: short turns, real questions, no speeches, no tool calls. Get "
            "to: what Barry actually wants, what matters most, who should own which "
            "piece, what done looks like and by when. NUMBERS: only ones that are "
            "actually in your notes. If a price, margin, budget or date is not "
            "there, say so and mark it as a question for Barry -- never supply one "
            "to keep the conversation moving. (The first huddle invented an '$85 "
            "anchor' that exists nowhere, and the whole brief was built on it.)"
        )

    backend, model = memory.get_active_generation()
    turns: list[tuple[str, str]] = []
    for i in range(HUDDLE_TURNS):
        speaker, agent, other = ("Victor", v, "Priya") if i % 2 == 0 else ("Priya", p, "Victor")
        rendered = "\n\n".join(f"{n}: {t}" for n, t in turns) or "(nothing said yet)"
        if i == 0:
            ask = (f"Barry gave you this: \"{b['brief']}\"\n\nOpen the conversation with Priya: "
                   "tell her what he wants and what you think matters most. A few sentences.")
        elif i == HUDDLE_TURNS - 1 and speaker == "Priya":
            ask = (f"The conversation so far:\n\n{rendered}\n\nYou are Priya. Close it: say back "
                   "the plan you are about to hand off -- who gets what, what done looks like. "
                   "A few sentences.")
        else:
            ask = (f"The conversation so far:\n\n{rendered}\n\nYou are {speaker}. Your next turn "
                   "-- a few sentences, a real question or a real answer.")
        tok = __import__("tracing").set_call_context("system")
        try:
            reply = await llm_router.generate(
                backend, _sys(agent, other), [{"role": "user", "content": ask}],
                model=model, use_tools=False, office_name=agent["office_name"])
        finally:
            __import__("tracing").reset_call_context(tok)
        if not reply or reply.startswith("["):
            break
        turns.append((speaker, reply.strip()))
    transcript = "\n\n".join(f"{n}: {t}" for n, t in turns)
    with memory.get_db() as conn:
        conn.execute("UPDATE briefs SET huddle=? WHERE id=?", (transcript[:6000], b["id"]))
    try:
        import json
        with open(os.path.join(_DATA, "huddles.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"when": _now(), "brief_id": b["id"], "turns": len(turns),
                                "transcript": transcript}) + "\n")
    except OSError:
        pass
    _log(f"brief #{b['id']}: huddle Victor<->Priya, {len(turns)} turns")
    return transcript


def name_of(office: str) -> str:
    return _FIRST_NAMES.get(office, office)


def label_of(office: str) -> str:
    return f"{name_of(office)} ({_ROLES.get(office, office)})"


# --- filing --------------------------------------------------------------------

def file_brief(from_office: str, to_office: str, brief: str, parent_id: int | None = None,
               not_before: str | None = None, proposed: bool = False) -> int:
    """File a brief on the board. `not_before` (UTC ISO) holds it until the
    office opens -- the on-call door (2026-09-11); None/'' = work it when quiet.
    `proposed` (2026-09-26) = filed as 'proposed' + a task_confirm card in his queue;
    nothing picks it up until he approves (confirm())."""
    with memory.get_db() as conn:
        depth = 0
        pid = parent_id
        while pid:
            row = conn.execute("SELECT parent_id FROM briefs WHERE id=?", (pid,)).fetchone()
            pid = row["parent_id"] if row else None
            depth += 1
        if depth >= MAX_DEPTH:
            parent_id = None          # stray, not a sub-brief -- the chain is deep enough
        cur = conn.execute(
            "INSERT INTO briefs (from_office, to_office, brief, parent_id, created_at, not_before, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (from_office, to_office, brief, parent_id, _now(), not_before or "",
             "proposed" if proposed else "open"))
        bid = cur.lastrowid
    _log(f"brief #{bid}: {from_office} -> {to_office}" + (f" (sub-brief of #{parent_id})" if parent_id else "")
         + (f" (held until {not_before})" if not_before else "")
         + (" (PROPOSED -- waits for Barry's confirm)" if proposed else "")
         + f": {brief[:80]!r}")
    if proposed:
        memory.queue_for_approval(
            _AGENT_ID_OF.get(from_office, "operations"), "task_confirm",
            f"{name_of(from_office)} wants to give {label_of(to_office)} this task. Approve to put it "
            f"on the board (it starts when the office is quiet); reject and it never runs.\n\n{brief}",
            file_path=f"brief:{bid}")
    refresh_ledger(from_office)
    refresh_ledger(to_office)
    return bid


_AGENT_ID_OF = {"CIO": "cio", "Operations": "operations", "BusinessOps": "business", "Legal": "legal",
                "Marketing": "marketing", "Creative": "creative", "MovieDirector": "movie",
                "Engineer": "engineer", "ilnora": "ilnora"}


def confirm(brief_id: int, yes: bool) -> str:
    """Barry's click on a task_confirm card: proposed -> open (worked when quiet) or declined."""
    with memory.get_db() as conn:
        row = conn.execute("SELECT status, from_office, to_office FROM briefs WHERE id=?", (brief_id,)).fetchone()
        if not row or row["status"] != "proposed":
            return f"brief #{brief_id} is not waiting for a confirm"
        conn.execute("UPDATE briefs SET status=? WHERE id=?", ("open" if yes else "declined", brief_id))
    _log(f"brief #{brief_id}: Barry {'CONFIRMED' if yes else 'declined'} it")
    refresh_ledger(row["from_office"])
    refresh_ledger(row["to_office"])
    return f"brief #{brief_id} {'is on the board' if yes else 'declined -- it will not run'}"


def chase(brief_id: int, by_office: str, note: str) -> dict:
    with memory.get_db() as conn:
        row = conn.execute("SELECT * FROM briefs WHERE id=?", (brief_id,)).fetchone()
        if not row:
            return {"status": "failed", "why": f"no brief #{brief_id}"}
        if row["status"] in ("proposed", "declined"):   # only Barry's confirm opens these
            return {"status": "failed", "why": f"brief #{brief_id} is {row['status']} -- only Barry's confirm can start it"}
        # A done brief CAN be chased -- "answered badly" is exactly the case
        # Priya's role names (2026-09-02: #4 came back with invented numbers).
        conn.execute("UPDATE briefs SET status='open', done_at=NULL, chaser=?, runs=0 WHERE id=?",
                     (f"CHASER from {label_of(by_office)} ({_now()[:16]}): {note.strip()}"[:600], brief_id))
    _log(f"brief #{brief_id} chased by {by_office}: {note[:80]!r}")
    refresh_ledger(row["to_office"])
    return {"status": "requeued", "note": f"Brief #{brief_id} is back at the top of {name_of(row['to_office'])}'s board with your chaser on it."}


# --- the ledger every seat carries ----------------------------------------------

def _age(iso: str) -> str:
    try:
        t = datetime.datetime.fromisoformat(iso)
        if t.tzinfo is None:
            t = t.replace(tzinfo=datetime.UTC)
        h = (datetime.datetime.now(datetime.UTC) - t).total_seconds() / 3600
        return f"{h*60:.0f}m ago" if h < 1 else (f"{h:.0f}h ago" if h < 48 else f"{h/24:.0f}d ago")
    except (TypeError, ValueError):
        return "?"


def ledger_text(office: str) -> str:
    cutoff = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=DONE_VISIBLE_DAYS)).isoformat()
    with memory.get_db() as conn:
        held = conn.execute(
            "SELECT * FROM briefs WHERE to_office=? AND (status IN ('open','working','waiting') "
            "OR (status IN ('done','failed') AND done_at > ?)) ORDER BY id DESC LIMIT 6",
            (office, cutoff)).fetchall()
        sent = conn.execute(
            "SELECT * FROM briefs WHERE from_office=? AND (status IN ('open','working','waiting') "
            "OR (status IN ('done','failed') AND done_at > ?)) ORDER BY id DESC LIMIT 6",
            (office, cutoff)).fetchall()
    lines = ["TEAM LOOPS -- your live position on the company task board (regenerated by the office; the team_status tool has the full list)."]
    lines.append("BRIEFS YOU HOLD:" if held else "BRIEFS YOU HOLD: none right now.")
    for r in held:
        st = r["status"].upper()
        lines.append(f"- #{r['id']} from {label_of(r['from_office'])}, {_age(r['created_at'])} [{st}]: {r['brief'][:280]}"
                     + (f" | {r['chaser'][:160]}" if r["chaser"] else "")
                     + (f" | your reply: {r['reply'][:200]}" if r["status"] == "done" else ""))
    lines.append("BRIEFS YOU SENT:" if sent else "BRIEFS YOU SENT: none right now.")
    for r in sent:
        st = r["status"].upper()
        rep = (r["reply"] or "").strip()
        lines.append(f"- #{r['id']} to {label_of(r['to_office'])}, {_age(r['created_at'])} [{st}]: {r['brief'][:160]}"
                     + (f" -> REPLY: {rep[:420]}" if rep and r["status"] in ("done", "waiting") else
                        (" -> not started yet" if r["status"] == "open" else "")))
    if office == "CIO":
        # THE CEO OVERSEES THE WHOLE BOARD (Barry, 2026-09-02: "Victor runs and
        # oversees things"). Compact company-wide view: counts + anything stale.
        stale_cut = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=24)).isoformat()
        with memory.get_db() as conn:
            counts = conn.execute(
                "SELECT status, COUNT(*) n FROM briefs WHERE status IN ('open','working','waiting') "
                "GROUP BY status").fetchall()
            stale = conn.execute(
                "SELECT id, from_office, to_office, created_at FROM briefs WHERE status IN "
                "('open','working','waiting') AND created_at < ? ORDER BY id LIMIT 5", (stale_cut,)).fetchall()
        summary = ", ".join(f"{r['n']} {r['status']}" for r in counts) or "nothing open"
        lines.append(f"THE WHOLE BOARD (you oversee it): {summary}."
                     + (" STALE >24h: " + "; ".join(
                         f"#{r['id']} {name_of(r['from_office'])}->{name_of(r['to_office'])} ({_age(r['created_at'])})"
                         for r in stale) if stale else ""))
    text = "\n".join(lines)
    return text[:LEDGER_CAP]


def refresh_ledger(office: str) -> None:
    # Taliyah keeps her board ledger too since 2026-10-10 (Barry: "Taliya is a part of this group")
    try:
        category = f"private:{office}"
        body = ledger_text(office)
        with memory.get_db() as conn:
            conn.execute("UPDATE facts SET status='superseded' WHERE category=? AND source_name=? AND status='active'",
                         (category, LEDGER_SOURCE))
        memory.add_fact(category, body, source_name=LEDGER_SOURCE,
                        title="Team loops -- briefs you hold and briefs you sent")
    except Exception as e:  # noqa: BLE001
        _log(f"ledger refresh failed for {office}: {e}")


# --- the worker -----------------------------------------------------------------

def _quiet_enough() -> bool:
    import ideation
    return (ideation._active_chat_count == 0 and (time.time() - ideation._last_activity_at) >= IDLE_SECONDS
            and not ideation._video_building())


def _pick() -> dict | None:
    """Oldest open brief, else oldest waiting brief whose children are all done.
    A brief with a future `not_before` (filed after hours at someone's office)
    is not picked until that time -- a forced tick (`work_one(bid, force=True)`)
    still can, because that is Barry saying now."""
    with memory.get_db() as conn:
        # ONE BRIEF AT A TIME (2026-09-11). The loop used to start a new brief
        # while another was still 'working' (a forced tick, or a run that
        # simply outlasted the 60s interval) -- two live turns on the single
        # Bonsai slot, which is the collision that fabricated #4's numbers on
        # 09-02. A fresh 'working' row means the GPU is taken; recover_stale
        # still frees anything older than 40 min, so a dead run cannot block
        # the board forever.
        live_cut = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=40)).isoformat()
        busy = conn.execute("SELECT id FROM briefs WHERE status='working' AND started_at >= ? LIMIT 1",
                            (live_cut,)).fetchone()
        if busy:
            return None
        row = conn.execute(
            "SELECT * FROM briefs WHERE status='open' "
            "AND (not_before IS NULL OR not_before='' OR not_before <= ?) "
            "ORDER BY id LIMIT 1", (_now(),)).fetchone()
        if row:
            return dict(row)
        for r in conn.execute("SELECT * FROM briefs WHERE status='waiting' ORDER BY id"):
            kids = conn.execute("SELECT status FROM briefs WHERE parent_id=?", (r["id"],)).fetchall()
            if kids and all(k["status"] in ("done", "failed") for k in kids):
                return dict(r)
    return None


def _children(bid: int) -> list[dict]:
    with memory.get_db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM briefs WHERE parent_id=? ORDER BY id", (bid,))]


_NAME_TO_OFFICE = {v: k for k, v in _FIRST_NAMES.items()}   # all ten (2026-10-10)


def named_seats(brief: str, holder: str, sender: str = "") -> list[str]:
    """Teammates a brief names by first name, other than the holder AND the
    sender. When a brief says 'Amara on the margin, Derek on the angle', those
    parts are theirs -- the holder answering for them is the fake interaction
    Barry does not want, and the first live run produced exactly that.
    The sender is excluded because Priya's briefs say 'once Priya delivers…'
    and Marcus's run was sent back for 'answering for Priya' (2026-09-02)."""
    import re
    out = []
    for name, office in _NAME_TO_OFFICE.items():
        if office in (holder, sender):
            continue
        if re.search(rf"\b{name}\b", brief, re.I):
            out.append(office)
    return out


def _message_for(b: dict, compile_mode: bool) -> str:
    sender = label_of(b["from_office"])
    if not compile_mode:
        named = named_seats(b["brief"], b["to_office"], b.get("from_office", ""))
        must = ""
        if named:
            must = ("THIS BRIEF NAMES " + " AND ".join(name_of(o).upper() for o in named)
                    + ". Those parts are THEIRS, not yours: call delegate_to for each of them "
                    "NOW with their piece, then do only your own part here (and say what you "
                    "handed off). Do not answer in their place -- a number or an angle you "
                    "invent for a teammate is a fake interaction, and the office will send "
                    "this back to you if you do.\n\n")
        huddle = ""
        if b.get("huddle"):
            huddle = ("YOU AND VICTOR WENT OVER THIS FIRST -- what you two said:\n"
                      f"{b['huddle']}\n\nHand it off from that plan.\n\n")
        return (
            f"BRIEF #{b['id']} FROM {sender.upper()}:\n{b['brief']}\n\n"
            + (f"{b['chaser']}\n\n" if b.get("chaser") else "")
            + huddle
            + must
            + "This is real work a teammate handed you, for the company, on Barry's behalf. "
            "Do it NOW, in this reply -- the actual deliverable (the draft, the numbers, the "
            "decision, the answer), not a plan to do it later. Use your tools where they "
            "apply. If a part of it genuinely belongs to another seat, hand THAT part to "
            "them with delegate_to (it becomes a sub-brief; you will be brought back to "
            "compile once they report) and do your own part here. If you cannot do it, say "
            "exactly what blocks you and what you need. Anything outbound still waits for "
            "Barry's approval as always. YOU DELIVER TO BARRY YOURSELF: this reply lands at "
            "your office for him to read (he is 'you' when you address him), and a copy goes "
            "to " + name_of(b["from_office"]) + " for tracking. Lead with the deliverable."
        )
    kids = _children(b["id"])
    reports = "\n\n".join(
        f"REPLY FROM {label_of(k['to_office']).upper()} (sub-brief #{k['id']}, {k['status']}):\n{(k['reply'] or '(no reply -- failed)').strip()}"
        for k in kids)
    return (
        f"YOUR TEAM REPORTED BACK on brief #{b['id']} from {sender.upper()}.\n"
        f"The original brief: {b['brief']}\n\n"
        f"Your interim reply was: {(b['reply'] or '').strip()[:800]}\n\n{reports}\n\n"
        "Now close the loop: compile the finished picture for " + name_of(b["from_office"])
        + " in this reply -- what each person delivered (they have already delivered it to "
        "Barry themselves), the result or decision it adds up to, and what is still open. "
        "Credit who did what. Do not delegate again unless something is genuinely unanswered."
    )


async def work_one(bid: int | None = None, force: bool = False) -> dict:
    """Work one brief. Returns what happened. Never raises."""
    import agents as _agents
    b = None
    if bid:
        with memory.get_db() as conn:
            row = conn.execute("SELECT * FROM briefs WHERE id=?", (bid,)).fetchone()
            b = dict(row) if row else None
    else:
        b = _pick()
    if not b:
        return {"worked": None, "why": "board is clear"}
    if not force and not _quiet_enough():
        return {"worked": None, "why": "Barry is mid-conversation -- holding"}
    # A forced tick is Barry saying "now", but it still cannot share the one
    # Bonsai slot with a brief already mid-run (2026-09-11).
    live_cut = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=40)).isoformat()
    with memory.get_db() as conn:
        other = conn.execute("SELECT id FROM briefs WHERE status='working' AND started_at >= ? AND id != ? LIMIT 1",
                             (live_cut, b["id"])).fetchone()
    if other:
        return {"worked": None, "why": f"brief #{other['id']} is being worked right now -- one at a time; try again in a few minutes"}
    if b["runs"] >= MAX_RUNS_PER_BRIEF:
        with memory.get_db() as conn:
            conn.execute("UPDATE briefs SET status='done', done_at=? WHERE id=?", (_now(), b["id"]))
        refresh_ledger(b["from_office"]); refresh_ledger(b["to_office"])
        return {"worked": b["id"], "why": "run cap reached -- closed with what it had"}

    compile_mode = b["status"] == "waiting"
    agent_id = _agents.agent_id_for_office(b["to_office"])   # hires too (2026-10-10)
    if not agent_id:
        with memory.get_db() as conn:
            conn.execute("UPDATE briefs SET status='failed', done_at=?, reply=? WHERE id=?",
                         (_now(), f"no such seat: {b['to_office']}", b["id"]))
        return {"worked": b["id"], "why": "unknown seat"}

    with memory.get_db() as conn:
        conn.execute("UPDATE briefs SET status='working', started_at=?, runs=runs+1 WHERE id=?",
                     (_now(), b["id"]))
    # THE HUDDLE: CEO -> assistant, top level, first run only.
    if (b["from_office"] == "CIO" and b["to_office"] == "Operations" and not compile_mode
            and not b.get("parent_id") and not b.get("huddle") and b["runs"] == 0):
        try:
            b["huddle"] = await _huddle(b)
        except Exception as e:  # noqa: BLE001
            _log(f"brief #{b['id']}: huddle failed ({e}) -- handing off without it")
    started = _now()
    _log(f"brief #{b['id']} -> {b['to_office']} {'COMPILE' if compile_mode else 'START'} (run {b['runs']+1})")
    t0 = time.time()
    reply, err = "", None
    try:
        async with httpx.AsyncClient(timeout=900) as cx:
            r = await cx.post("http://127.0.0.1:8420/api/chat",
                              json={"agent_id": agent_id, "message": _message_for(b, compile_mode),
                                    "task": True, "brief_id": b["id"]})
        r.raise_for_status()
        _j = r.json() or {}
        reply = (_j.get("reply") or "").strip()
        tools_ran = list(_j.get("tool_calls") or [])
        fell_back = bool(_j.get("bonsai_fell_back"))
        if not reply or reply.startswith("["):
            err = reply or "empty reply"
        elif fell_back and not compile_mode:
            # NEVER ACCEPT BOARD WORK FROM THE FALLBACK MODEL (2026-09-11).
            # Measured twice: brief #4 (09-02) and #27 run 1+2 today -- on the
            # 9b a research brief comes back with invented suppliers, invented
            # landed costs, invented MOQs, written confidently. Bonsai was
            # merely tripped for ten minutes; the honest move is to wait, not
            # to file a fiction on Barry's desk. A fallback run is a failed
            # run: re-queued (its run does not count), retried when quiet.
            err = "ran on the fallback model (Bonsai unavailable) -- not accepted for board work"
    except Exception as e:  # noqa: BLE001
        # The TYPE, not just the text (2026-09-28): httpx.ReadTimeout's text is
        # EMPTY, so err was "" and brief #50's 900s timeout was filed as
        # "done in 900s (0 chars)" -- Barry's barcode job vanished as a success.
        err = (f"{type(e).__name__}: {e}".strip(": ").strip() or "request failed")[:300]
        tools_ran, fell_back = [], False
    # NO SILENT DONE (2026-09-28): whatever path got here, an empty reply is a
    # failed run, never a delivery.
    if not err and not (reply or "").strip():
        err = "empty reply"
    took = time.time() - t0
    # EVERY RUN'S REPLY IS KEPT ON DISK (2026-09-11). The row holds only the
    # latest reply, a send-back overwrites it, and traces keep 800 chars --
    # so #27's run-one document was gone before anyone could file it. Cheap,
    # append-only, never in a prompt.
    try:
        _rd = os.path.join(_DATA, "brief_runs")
        os.makedirs(_rd, exist_ok=True)
        with open(os.path.join(_rd, f"brief{b['id']}_run{b['runs'] + 1}_{_now()[:19].replace(':', '')}.md"),
                  "w", encoding="utf-8") as _fh:
            _fh.write(f"# brief #{b['id']} -> {b['to_office']} run {b['runs'] + 1}\n"
                      f"tools: {tools_ran}  fell_back: {fell_back}  err: {err or ''}\n\n{reply}")
    except OSError:
        pass

    new_kids = [k for k in _children(b["id"]) if k["created_at"] >= started]
    named = [] if compile_mode else named_seats(b["brief"], b["to_office"], b.get("from_office", ""))
    # UNGROUNDED NUMBERS (2026-09-02): Priya's first sourcing reply listed
    # landed costs, margins and sample prices for named suppliers with NO tool
    # call behind it -- the 9b fallback made them up, and it reached Barry's
    # office as a deliverable. A reply full of figures from a run that looked
    # nothing up is a fake; send it back once with the reason on top.
    import re as _re
    ungrounded = (not compile_mode and not tools_ran
                  and len(_re.findall(r"\$\s?\d|\d+(?:\.\d+)?\s?%|\bMOQ\b", reply or "")) >= 3)
    # THE DELIVERABLE IS A FILE (2026-09-11, brief #27): the brief said "deliver
    # it as a FILE on Barry's DESK with send_file_to_barry"; Priya searched for
    # real, then wrote "I've saved the shortlist to my notes" (no save_note
    # either) and "ready for your desk". A required file that was never written
    # is a delivery claim with nothing behind it -- send it back once.
    file_required = (not compile_mode and bool(_re.search(r"send_file_to_barry|\bFILE\b[^.]{0,40}\bDESK\b", b["brief"] or "")))
    file_missing = file_required and "send_file_to_barry" not in tools_ran
    # THE SAME NET FOR A PICTURE (2026-09-11, Sophie's #20-26): her brief asked
    # every seat to describe their home picture; only Victor called
    # change_my_picture -- three others described the room in prose back to
    # her, which is the relay-paraphrase path this build forbids. A brief
    # about someone's picture is delivered by that tool, or it is not
    # delivered.
    pic_required = (not compile_mode and bool(_re.search(
        r"change_my_picture|\b(?:home|office|self|out)\s+pictures?\b|\byour\s+picture\b|\bscene\s+update\b",
        b["brief"] or "", _re.I)))
    pic_missing = pic_required and "change_my_picture" not in tools_ran
    # THE OFFICE FILES THE DOCUMENT SHE WROTE (2026-09-11, #27 runs 3-5): with
    # six rounds she did sixteen real searches on Bonsai and wrote the whole
    # shortlist as a ```markdown``` document marked "Draft (not sent)" -- and
    # still never called send_file_to_barry. Three runs of the same shape.
    # Sending it back a fourth time buys nothing; the deliverable EXISTS, in
    # her words. So when a file was required and the reply carries a fenced
    # document, the office writes THAT, byte for byte, to her shelf through
    # the same write_file the tool uses -- exactly what queueing the home
    # pictures verbatim did. A finding about the content (a number she put in
    # Barry's mouth) rides in the file's "what it is" line, never in the file.
    office_filed = None
    if file_missing and not err:
        _fm = _re.search(r"```(?:markdown|md)?\s*\n(.*?)```", reply or "", _re.S)
        _doc = (_fm.group(1).strip() if _fm else "")
        if len(_doc) >= 600:
            _h = _re.search(r"^#+\s*(.+?)\s*$", _doc, _re.M)
            _stem = _re.sub(r"[^a-z0-9]+", "-", (_h.group(1) if _h else f"brief-{b['id']}-deliverable").lower()).strip("-")[:60]
            _what = (f"Filed by the office from {name_of(b['to_office'])}'s reply to brief #{b['id']} -- "
                     f"the document exactly as written; send_file_to_barry was never called.")
            if attributed:
                _what += (" OFFICE NOTE: " + ", ".join(sorted(set(attributed))[:4])
                          + " is presented as something Barry or Victor asked for and is in neither "
                            "his brief nor the huddle -- treat as the seat's own assumption.")
            office_filed = agent_files.write_file(b["to_office"], f"{_stem}-{_now()[:10]}.md", _doc, what_it_is=_what)
            if office_filed.get("error"):
                _log(f"brief #{b['id']}: office file write failed: {office_filed['error']}")
                office_filed = None
            else:
                _log(f"brief #{b['id']}: office filed the fenced document to the DESK ({len(_doc)} chars): "
                     f"{office_filed.get('filename') or office_filed.get('path') or ''}")
                file_missing = False
                attributed = []          # noted on the file, not a send-back
    # NUMBERS PUT IN BARRY'S MOUTH (2026-09-11, same run): "$55-60 target",
    # "under 500 pieces like Victor requested" -- figures in neither Barry's
    # brief nor the huddle, presented as his constraints. A number the seat
    # found on a supplier page is fine; a number it attributes to Barry, Victor
    # or the brief must actually be there. Mechanical, sentence-level.
    _given = (b["brief"] or "") + " " + (b.get("huddle") or "")
    attributed = []
    for sent in _re.split(r"(?<=[.!?])\s+", reply or ""):
        if not _re.search(r"\b(?:barry|victor|the brief|target|threshold|requested|asked for)\b", sent, _re.I):
            continue
        for fig in _re.findall(r"\$\s?\d[\d,]*(?:\.\d+)?(?:\s?-\s?\d[\d,]*)?|\b\d{2,5}\s*(?:pieces|units|pcs)\b", sent):
            key = _re.sub(r"[\s,]", "", fig)
            if key.replace("$", "") and key.split("-")[0] not in _re.sub(r"[\s,]", "", _given):
                attributed.append(fig.strip())
    attributed = attributed if not compile_mode else []
    # INVENTED SUPPLIERS (2026-09-11): a named domain that does not exist in
    # DNS is a company the seat made up. Cheap; see _dead_domains for what it
    # cannot catch. Only on runs that were supposed to research.
    dead = _dead_domains(reply) if (not compile_mode and not err) else []
    if dead:
        _log(f"brief #{b['id']}: domains that do not resolve: {dead}")
    with memory.get_db() as conn:
        if err and (b["runs"] + 1 < MAX_RUNS_PER_BRIEF or err.startswith("ran on the fallback")):
            # A dead run (Bonsai hiccup, empty reply, timeout) is retried, not
            # buried -- Derek's #8 died with 0 chars on its first pass.
            # A FALLBACK run does not count at all and waits out the breaker
            # window before the next try (2026-09-11).
            if err.startswith("ran on the fallback"):
                hold = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=8)).isoformat()
                conn.execute("UPDATE briefs SET status='open', runs=MAX(runs-1,0), not_before=?, chaser=? WHERE id=?",
                             (hold, "(previous attempt ran on the fallback model and was discarded -- "
                                    "do the research for real this time)", b["id"]))
            else:
                conn.execute("UPDATE briefs SET status='open', chaser=? WHERE id=?",
                             (f"(previous run failed: {err[:160]} -- retrying)", b["id"]))
            outcome = f"run failed ({err[:60]}) -- re-queued"
        elif err:
            conn.execute("UPDATE briefs SET status='failed', done_at=?, reply=? WHERE id=?",
                         (_now(), f"[failed: {err}]", b["id"]))
            outcome = "failed"
            _flag_failed_brief(b, err)
        elif ungrounded and b["runs"] + 1 < MAX_RUNS_PER_BRIEF:
            conn.execute("UPDATE briefs SET status='open', reply=?, chaser=? WHERE id=?",
                         (reply, f"SENT BACK BY THE OFFICE ({_now()[:16]}): your reply is full of prices, "
                                 f"costs or percentages but you looked NOTHING up (no tool ran"
                                 + (", and you were on the fallback model" if fell_back else "")
                                 + "). Research for real -- search_web, lookup_product, sales_summary -- "
                                 "cite what you looked at, and never present a figure you did not find.",
                          b["id"]))
            outcome = "sent back -- numbers with no research behind them"
        elif (file_missing or pic_missing or attributed or dead) and b["runs"] + 1 < MAX_RUNS_PER_BRIEF:
            why = []
            if pic_missing:
                why.append("this is about your picture and you never called change_my_picture -- "
                           "a description in prose changes nothing. Call it NOW with the slot and "
                           "your description as you wrote it; it goes to Barry verbatim")
            if dead:
                why.append("these domains you named do not exist: " + ", ".join(dead[:4])
                           + " -- a supplier you cannot open is not a supplier; remove it and "
                             "only list companies whose site you actually got a result from")
            if file_missing:
                why.append("the deliverable is a FILE on Barry's DESK and you never called "
                           "send_file_to_barry -- write the shortlist as a real .md file NOW "
                           "(everything you found, every gap named), then reply")
            if attributed:
                why.append("you presented " + ", ".join(sorted(set(attributed))[:4])
                           + " as something Barry or Victor asked for -- it is in neither his "
                             "brief nor the huddle. Drop it or say plainly it is your own assumption")
            conn.execute("UPDATE briefs SET status='open', reply=?, chaser=? WHERE id=?",
                         (reply, f"SENT BACK BY THE OFFICE ({_now()[:16]}): " + "; ".join(why) + ".",
                          b["id"]))
            outcome = "sent back -- " + " + ".join(
                x for x in (("invented domains" if dead else ""),
                            ("no file written" if file_missing else ""),
                            ("picture not queued" if pic_missing else ""),
                            ("numbers put in Barry's mouth" if attributed else "")) if x)
        elif named and not new_kids and not compile_mode and b["runs"] + 1 < MAX_RUNS_PER_BRIEF:
            # ANSWERED FOR TEAMMATES -- the fake interaction. Send it back once
            # with the reason on top; the second pass has the same rule.
            who = " and ".join(name_of(o) for o in named)
            conn.execute("UPDATE briefs SET status='open', reply=?, chaser=? WHERE id=?",
                         (reply, f"SENT BACK BY THE OFFICE ({_now()[:16]}): you answered for {who} "
                                 f"yourself instead of briefing them. Delegate_to each of them now "
                                 f"with their piece; your draft is kept and you will compile when they report.",
                          b["id"]))
            outcome = f"sent back -- answered for {who} without delegating"
        elif new_kids and not compile_mode:
            conn.execute("UPDATE briefs SET status='waiting', reply=? WHERE id=?", (reply, b["id"]))
            outcome = f"waiting on {len(new_kids)} sub-brief(s)"
        else:
            conn.execute("UPDATE briefs SET status='done', done_at=?, reply=? WHERE id=?",
                         (_now(), reply, b["id"]))
            outcome = "done"
    _log(f"brief #{b['id']} {outcome} in {took:.0f}s ({len(reply)} chars)")

    refresh_ledger(b["from_office"])
    refresh_ledger(b["to_office"])
    if outcome == "done" and not err:
        _file_worknote(b, reply)
    return {"worked": b["id"], "outcome": outcome, "seconds": round(took), "reply_chars": len(reply)}


def _flag_failed_brief(b: dict, err: str) -> None:
    """A brief that failed for good tells Barry (2026-09-28, "I need them to be
    totally reliable"). It lands as a work note at the seat's office, so the
    green dot lights -- written by the office, labelled as such, never in the
    seat's voice."""
    try:
        import reflect
        today = datetime.date.today().isoformat()
        text = (f"[Office note -- brief #{b['id']} FAILED, {today}]\n\n"
                f"{name_of(b['to_office'])} could not finish brief #{b['id']} from "
                f"{name_of(b['from_office'])} after {b['runs'] + 1} runs. Last error: {err[:200]}\n\n"
                f"Nothing was delivered. The brief: {(b['brief'] or '')[:400]}")
        reflect._store(b["to_office"], f"worknote-team-{b['id']}-failed.md",
                       f"Brief #{b['id']} failed -- nothing delivered", text)
        _log(f"brief #{b['id']}: FAILED for good -- flagged to Barry at {b['to_office']}'s office")
    except Exception as e:  # noqa: BLE001
        _log(f"failed-brief flag failed for #{b['id']}: {e}")


def _file_worknote(b: dict, reply: str) -> None:
    """Barry sees the finished work at the OFFICE of whoever did it (green
    dot), verbatim. One fact per brief so several in a day do not overwrite."""
    try:
        import reflect
        body, _fixed = reflect._scrub_delivery_claims(reply)
        today = datetime.date.today().isoformat()
        stamp = (f"[{name_of(b['to_office'])}, closing brief #{b['id']} from "
                 f"{name_of(b['from_office'])}, {today}]\n\n{body}")
        reflect._store(b["to_office"], f"worknote-team-{b['id']}.md",
                       f"{name_of(b['to_office'])} finished a brief from {name_of(b['from_office'])} -- #{b['id']}",
                       stamp)
    except Exception as e:  # noqa: BLE001
        _log(f"worknote failed for #{b['id']}: {e}")


def status(office: str | None = None, limit: int = 30) -> dict:
    cutoff = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=7)).isoformat()
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM briefs WHERE (status IN ('open','working','waiting') OR done_at > ?) "
            "ORDER BY id DESC LIMIT ?", (cutoff, limit)).fetchall()
    out = []
    for r in rows:
        if office and office not in (r["from_office"], r["to_office"]):
            continue
        out.append({"id": r["id"], "from": name_of(r["from_office"]), "to": name_of(r["to_office"]),
                    "status": r["status"], "age": _age(r["created_at"]),
                    "brief": r["brief"][:240], "reply": (r["reply"] or "")[:400],
                    "sub_brief_of": r["parent_id"], "chaser": r["chaser"] or None,
                    "huddle": (r["huddle"] or None) if "huddle" in r.keys() else None})
    open_n = sum(1 for o in out if o["status"] in ("open", "working", "waiting"))
    return {"open": open_n, "briefs": out,
            "note": "Statuses: open = not started; working = being done now; waiting = the seat "
                    "delegated part of it and will compile when sub-briefs report; done = the reply "
                    "is in the sender's TEAM LOOPS. Stale open items can be re-queued with chase_brief."}


def recover_stale(startup: bool = False) -> int:
    """A backend restart kills a brief mid-run and leaves it 'working' forever.
    On every tick anything working for > 40 min goes back to open -- its run
    does not count, its reply is kept as a draft. At STARTUP every 'working'
    row is freed regardless of age (2026-09-11): the process that was running
    it is gone, and with the one-at-a-time guard a fresh-looking zombie would
    otherwise block the whole board for up to 40 minutes after each restart."""
    cut = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=40)).isoformat()
    with memory.get_db() as conn:
        if startup:
            # Only rows that were already running when THIS process started --
            # a forced tick that began after boot is live and must be left
            # alone (the first version freed #27 mid-run, 2 min after boot).
            rows = conn.execute("SELECT id, to_office, from_office FROM briefs WHERE status='working' "
                                "AND (started_at IS NULL OR started_at < ?)", (_BOOT,)).fetchall()
        else:
            rows = conn.execute("SELECT id, to_office, from_office FROM briefs WHERE status='working' "
                                "AND (started_at IS NULL OR started_at < ?)", (cut,)).fetchall()
        for r in rows:
            conn.execute("UPDATE briefs SET status='open', runs=MAX(runs-1,0) WHERE id=?", (r["id"],))
    for r in rows:
        _log(f"brief #{r['id']} was left 'working' (restart?) -- back to open")
        refresh_ledger(r["to_office"]); refresh_ledger(r["from_office"])
    return len(rows)


async def run_teamwork_loop() -> None:
    await asyncio.sleep(STARTUP_DELAY_SECONDS)
    try:
        recover_stale(startup=True)
    except Exception as e:  # noqa: BLE001
        _log(f"recover_stale failed: {e}")
    while True:
        try:
            recover_stale()
            await work_one()
        except Exception as e:  # noqa: BLE001
            _log(f"loop error (living on): {e}")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
