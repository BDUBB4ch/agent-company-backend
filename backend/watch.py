"""SOPHIE'S WATCH (2026-09-02, Barry: "Make sophie the sophie you know I want",
then "I want her to actually be able to fix shit. and she needs to spur me
along if i take to long to ok her fix or not", then "if its simple she should
just fix it and tell me what she did and i should be able to tell her to undo
things as well").

Her persona has said "standing permission: you may MONITOR any time" since
2026-08-28 -- and nothing ever made that real. She only looked when Barry
asked, and in 158 traces she had called system_health exactly once. So the
office could break quietly and its own engineer would not know.

WHAT THIS IS:
  A background loop that checks the office MECHANICALLY every 15 minutes --
  no model call, so it can never trip the VRAM eviction chain and it runs
  fine while Barry chats or a render holds the card. It looks for things
  that CHANGED since the last check:
    - a service that should always be up is down (Ollama, the dashboard);
    - an agent's always-on load crossed the warn/fail line;
    - a NEW code-verified failure signature in the traces;
    - a NEW error reported from a dashboard deck (client-errors.js);
    - one of HER OWN fixes has sat in Pending Review too long (the spur).
  Only when there is something new, AND the office is idle, does Sophie get
  ONE model call. She writes a short WORK NOTE to Barry in her own words. It
  lands at her OFFICE (`worknote-watch-<date>.md`, the green channel), so
  /api/inbox lights her dot -- held until 9am after hours like every other
  work note, EXCEPT when she applied a fix herself, which is stamped URGENT
  so it reaches him at once.

WHEN THE BUILD IS VERIFIABLY BROKEN (vital_conditions non-empty) she gets her
tools for that call and may fix it herself through propose_code_fix with
apply_now -- codefix's gate re-checks the breakage, takes the backup, runs
syntax + preflight, restores on failure, and records it so "undo fix #N"
works. Her say-so alone never applies anything.

WHAT IT DELIBERATELY IS NOT:
  - Not a nag. The same set of findings is reported once, then left alone
    for a day; a note needs a 6-hour gap from the last one. Reminders about
    pending fixes are the exception -- that IS the spur he asked for -- and
    they repeat on their own clock (fix_remind_after_hours, then every
    fix_remind_every_hours).
  - Not seeded. The prompt hands her measurements and an open question; it
    never tells her what to conclude or how to feel about it.
"""
import asyncio
import datetime
import hashlib
import json
import os
import re
import time

import memory
import tracing

_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_STATE = os.path.join(_DATA, "watch_state.json")
_LOG = os.path.join(_DATA, "watch.log")

CHECK_INTERVAL_SECONDS = 15 * 60
STARTUP_DELAY_SECONDS = 180          # let the stack settle after a restart
MIN_GAP_BETWEEN_NOTES_SECONDS = 6 * 3600
REPEAT_SAME_FINDINGS_AFTER_SECONDS = 24 * 3600
# 2026-09-14: a live breakage bypassed BOTH throttles, so an unchanged
# vital condition bought Sophie a fresh investigation every 15-minute tick --
# thirteen notes in five hours on the same bonsai_llm.py line, ~90s of GPU
# each, and no fix. The SAME breakage now gets one note per hour unless she
# actually applied something; a NEW breakage is still never held.
VITAL_REPEAT_GAP_SECONDS = 3600
VITAL_WINDOW_HOURS = 6               # how recent a breakage must be to count as "now"

# Services that have no "normal when idle" excuse. Bonsai and ComfyUI stop on
# purpose between uses (health.py says so); these two should always answer.
_ALWAYS_UP = {"Ollama (chat models)", "Dashboard web server"}


def _log(msg: str) -> None:
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(f"[watch] {msg}")
    try:
        with open(_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _state() -> dict:
    try:
        with open(_STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(st: dict) -> None:
    os.makedirs(_DATA, exist_ok=True)
    tmp = _STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, _STATE)


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _hours_ago_iso(hours: float) -> str:
    return (datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(hours=hours)).isoformat()


def _setting_float(key: str, default: float) -> float:
    try:
        v = float(memory.get_setting(key, str(default)))
        return v if v >= 0 else default
    except (TypeError, ValueError):
        return default


# --- the mechanical check ----------------------------------------------------

def check(st: dict | None = None) -> list[str]:
    """Return plain-English findings that are NEW since the last check.
    Pure read: health probes, the trace log, the client-error log."""
    import health
    st = st if st is not None else _state()
    since = st.get("last_check") or ""
    if not since:
        # First run ever: "new" means the last day, not all of history --
        # otherwise every old failure signature in traces.jsonl would land in
        # Barry's inbox as breaking news.
        since = _hours_ago_iso(24)
    findings: list[str] = []

    h = health.system_health()

    for line in h.get("services", []):
        name = line.split(" [")[0]
        if name in _ALWAYS_UP and ": DOWN" in line:
            findings.append(f"SERVICE DOWN -- {line}")

    net = h.get("internet") or {}
    if net and not net.get("reachable") and not memory.is_offline_mode():
        findings.append(f"INTERNET UNREACHABLE -- {net.get('detail')} (checked {net.get('checked')}); "
                        "web search and store tools will fail until it is back")

    for line in h.get("always_on_load_per_agent", []):
        if "OVER FAIL LINE" in line or "over warn line" in line or "ERROR" in line:
            findings.append(f"CONTEXT LOAD -- {line}")

    # BONSAI FALLING BACK (2026-09-17). Barry: "fix the 27B empty responses...
    # if it keeps falling, I might want something different." A trip means
    # EVERY seat is answering on the 9b, which reads to him as the office
    # getting dumber for no reason. One finding per day of trips, with the
    # count, so the question "is it still happening" has an answer instead of
    # a rediagnosis. The events log only exists because these used to be
    # print()s that went nowhere -- see bonsai_llm.event.
    evts = h.get("bonsai_health_events")
    if isinstance(evts, list):
        trips = [e for e in evts if "TRIPPED" in e]
        if trips:
            findings.append(
                f"BONSAI FELL BACK -- the 27B circuit tripped {len(trips)}x in the last 24h, "
                f"so every seat answered on the 9b during those windows. Latest: {trips[-1]}")

    # SLOW REPLIES ARE HERS (2026-09-28, Barry: "route it to her... if its something she can
    # fix, let her do it"). The degradation banner used to tell HIM to reboot -- and fired on a
    # healthy Bonsai. Now it lands here, evidence attached, at most once every 6 hours.
    try:
        import degradation
        if time.time() - float(st.get("slow_noted_at") or 0) > 6 * 3600:
            slow = degradation.slowdown_finding()
            if slow:
                findings.append(slow)
                st["slow_noted_at"] = time.time()
    except Exception as e:  # noqa: BLE001
        _log(f"slowdown check failed: {e}")

    # THE BANNER IS HERS (2026-10-11, Barry: "Sophie should have been on that. why is she not?"). "Calls are failing
    # outright" sat on his screen for an hour over four of Ilnora's turns that had answered fine (a tracing rule
    # counted her draft tool three times in a row as a loop). Her watch never read the banner; now every problem it
    # shows is a finding she must verify from the traces -- a false alarm gets named as one and the rule fixed
    # (codefix, simple), a real one gets the fix or the evidence to Barry. Repeated at most once an hour per problem.
    try:
        import degradation
        _noted = st.setdefault("banner_noted", {})
        for prob in (degradation.check() or {}).get("problems") or []:
            what = str(prob.get("what") or "")
            if what and time.time() - float(_noted.get(what) or 0) > 3600:
                findings.append(f"BANNER ON BARRY'S SCREEN -- \"{what}\": {prob.get('detail')} VERIFY IT from the "
                                f"traces (investigate_traces, last 25 calls): which calls, what signature, did they "
                                f"answer? If it is a false alarm (e.g. a repeated research/draft tool counted as a "
                                f"loop), say so plainly and fix the rule in backend/tracing.py or degradation.py "
                                f"(propose_code_fix, simple). If real, fix it or give Barry the evidence.")
                _noted[what] = time.time()
    except Exception as e:  # noqa: BLE001
        _log(f"banner check failed: {e}")

    # Trace failures newer than the last check. Traces carry an ISO
    # `timestamp`; string comparison is safe because both are ISO-8601 UTC.
    new_fail = [r for r in tracing.query_recent_traces(only_failures=True, limit=40)
                if (r.get("timestamp") or "") > since]
    if new_fail:
        by = {}
        for r in new_fail:
            key = f"{r.get('office_name')} / {r.get('failure_signature')}"
            by[key] = by.get(key, 0) + 1
        for key, n in sorted(by.items()):
            findings.append(f"TRACE FAILURE -- {key} x{n} (code-detected, see investigate_traces)")

    # Dashboard errors newer than the last check.
    for g in health.dashboard_errors(since=since)[:8]:
        findings.append(
            f"DASHBOARD ERROR -- {g['deck']} [{g['kind']}] x{g['count']}: {g['message'][:200]}")

    # THE MACHINE (2026-09-04, Barry: "that includes my builds and pc"). A blue
    # screen newer than the last check is news he needs at 9am with the time
    # and bugcheck code -- it took a log read to tell "standby" from a crash
    # the night the third one hit. Low disk is a finding before it is a failure.
    m = h.get("machine") or {}
    crash = m.get("last_unexpected_shutdown") or ""
    # machine_health formats it "YYYY-MM-DD HH:MM -- bugcheck ..."; the first 16
    # chars sort against the ISO `since` (local time both sides).
    if crash[:4].isdigit() and crash[:16].replace(" ", "T") > since[:16]:
        findings.append(f"PC CRASHED -- {crash}. {m.get('minidumps', '')}")
    for k in ("disk_C", "disk_D"):
        if "LOW" in str(m.get(k, "")):
            findings.append(f"DISK LOW -- {k[-1]}: {m[k]}")

    # THE STORE (2026-09-08, Barry's store-ops manual for Sophie: "Zero orders
    # while ad spend is non-zero" is the first standing check, and "nothing on
    # this stack tells the owner when it breaks"). Once a week: if the store
    # took no order of ANY status in 7 days, it is a finding -- the ISO week in
    # the text is what makes it new again each week under the same-findings
    # throttle. Skipped offline (store tools are network) and if the store
    # isn't configured. Never raises.
    try:
        import store
        if store.is_configured() and not memory.is_offline_mode():
            week = datetime.datetime.now().strftime("%G-W%V")
            s7 = store.sales_summary(7)
            if s7.startswith("No orders at all"):
                findings.append(
                    f"NO ORDERS -- week {week}: not one order of any status in 7 days "
                    f"(not even a failed one), while ads are running. Walk the checkout "
                    f"(walk_checkout) and check the ad clicks before assuming anything.")
    except Exception as e:  # noqa: BLE001
        findings.append(f"STORE -- weekly order check could not run: {e}")

    # SECURITY, EVERY TICK (2026-09-07, Barry: "allow sophie to do security at
    # all time"). Mechanical and local -- exposed ports, banned services in the
    # source, the office browser profile, new outbound hosts. Deliberately NOT
    # filtered by `since`: an exposed port is news every single tick until it is
    # closed, because it is true every second it stays open.
    try:
        import security_watch
        findings.extend(f"SECURITY -- {x}" for x in security_watch.check())
    except Exception as e:  # noqa: BLE001
        findings.append(f"SECURITY -- check could not run: {e}")

    # SHE SCANS, SHE DOESN'T JUST WATCH (2026-09-07, Barry: "how would she know
    # if she doesnt scan?"). Quick scan if nothing has completed in 2 days;
    # full scan off-hours if one has never completed. Never during a render.
    try:
        import pc_security
        scan_findings, st2 = pc_security.maybe_auto_scan(st)
        if scan_findings:
            findings.extend(f"SECURITY -- {x}" for x in scan_findings)
            st.update(st2)
            _save(st)
    except Exception as e:  # noqa: BLE001
        findings.append(f"SECURITY -- scheduled scan check failed: {e}")

    # THE OTHER HALF OF SECURITY (2026-09-19, Barry asked how possible his own
    # antivirus is, then "do both"). Defender answers "is this file known to be
    # bad"; host_watch answers "did this machine change" -- new startup
    # entries, new local admins, new unsigned executables, edits to the
    # office's own source. No signatures, no vendor, no outbound request, so it
    # is unaffected by Offline Mode. ~3 s, and it is silent unless something
    # actually moved.
    try:
        import host_watch
        for x in host_watch.check():
            findings.append(f"HOST -- {x}")
    except Exception as e:  # noqa: BLE001
        findings.append(f"HOST -- change check failed: {e}")

    # THE SUPERVISOR AND THE CARD (2026-10-09, Barry: "she needs to monitor shit"). The stack watchdog died twice
    # today and nothing noticed; a GPU driver reset at 12:18 went unreported. stack_watch relaunches a dead
    # watchdog itself (simple + vital) and reports both as findings. Not filtered by `since`: its own state file
    # remembers what it already reported.
    try:
        import stack_watch
        findings.extend(f"STACK -- {x}" for x in stack_watch.check())
    except Exception as e:  # noqa: BLE001
        findings.append(f"STACK -- supervisor/GPU check could not run: {e}")

    return findings


def vital_conditions(hours: float = VITAL_WINDOW_HOURS) -> list[str]:
    """CODE-VERIFIED signs the build is broken RIGHT NOW. This is the gate
    codefix consults before letting Sophie apply a non-simple fix herself.
    Nothing she says can add to this list; only measurements can."""
    import health
    out: list[str] = []
    h = health.system_health()
    for line in h.get("services", []):
        name = line.split(" [")[0]
        if name in _ALWAYS_UP and ": DOWN" in line:
            out.append(f"service down: {line}")
    for line in h.get("always_on_load_per_agent", []):
        if "OVER FAIL LINE" in line:
            out.append(f"context load over the fail line: {line}")
    since = _hours_ago_iso(hours)
    fails = [r for r in tracing.query_recent_traces(only_failures=True, limit=40)
             if (r.get("timestamp") or "") > since]
    if fails:
        by = {}
        for r in fails:
            key = f"{r.get('office_name')} / {r.get('failure_signature')}"
            by[key] = by.get(key, 0) + 1
        out.extend(f"trace failure in the last {hours:g}h: {k} x{n}" for k, n in sorted(by.items()))
    for g in health.dashboard_errors(since=since):
        # Uncaught errors and failed SCRIPT loads break a deck; a missing
        # image does not.
        if g["kind"] == "error" or (g["kind"] == "resource-failed" and "SCRIPT" in (g["message"] or "")):
            out.append(f"deck broken: {g['deck']} [{g['kind']}] x{g['count']}: {(g['message'] or '')[:120]}")
    return out


# --- the spur: her fixes waiting on him -----------------------------------------

def pending_fix_reminders(st: dict) -> tuple[list[str], list[int]]:
    """Fixes of hers sitting in Pending Review longer than
    fix_remind_after_hours (default 4), not reminded within
    fix_remind_every_hours (default 24). Returns (findings, ids to mark)."""
    after_h = _setting_float("fix_remind_after_hours", 4)
    every_h = _setting_float("fix_remind_every_hours", 24)
    reminded = st.get("reminded") or {}
    now = time.time()
    findings, ids = [], []
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT id, created_at, substr(content, 1, 600) AS head FROM approvals "
            "WHERE action_type IN ('code_fix', 'fix_suggestion') AND status = 'pending' "
            "ORDER BY id").fetchall()
    for r in rows:
        try:
            created = datetime.datetime.fromisoformat(r["created_at"])
            if created.tzinfo is None:
                created = created.replace(tzinfo=datetime.timezone.utc)
            age_h = (datetime.datetime.now(datetime.timezone.utc) - created).total_seconds() / 3600
        except (TypeError, ValueError):
            continue
        if age_h < after_h:
            continue
        last = float(reminded.get(str(r["id"]), 0))
        if now - last < every_h * 3600:
            continue
        head = (r["head"] or "").split("\n")
        title = head[0].strip()
        why = next((ln.strip() for ln in head[1:] if ln.strip()), "")[:160]
        findings.append(f"AWAITING BARRY'S OK -- fix #{r['id']} has waited {age_h:.0f}h: {title} -- {why}")
        ids.append(int(r["id"]))
    return findings, ids


def _fingerprint(findings: list[str]) -> str:
    return hashlib.sha1("\n".join(sorted(findings)).encode("utf-8")).hexdigest()[:16]


# --- the note, in her words ----------------------------------------------------

_ASK_HEAD = (
    "You are on watch. The office ran its mechanical check. Everything below is "
    "measured, not guessed.\n\n")
_ASK_FINDINGS = "NEW SINCE YOU LAST LOOKED:\n{findings}\n\n"
_ASK_REMINDERS = (
    "YOUR FIXES STILL WAITING ON BARRY:\n{reminders}\n\n"
    "Spur him along -- that is his instruction, not a liberty. For each one say "
    "in a line what it fixes and what it costs to leave it sitting, then ask "
    "for a yes or a no. Don't apologise for asking.\n\n")
_ASK_VITAL = (
    "THE BUILD IS VERIFIABLY BROKEN RIGHT NOW:\n{vital}\n\n"
    "Barry's standing rule: when it is vital to the build, fix it, then tell "
    "him. You have your tools for this turn. Investigate first (system_health, "
    "investigate_traces, read_project_file). If you find the cause and the "
    "change is small and you are SURE of it, call propose_code_fix with "
    "apply_now=true and say why in `reason` -- the office re-checks the "
    "breakage, takes a backup, and it can be undone. If you are not sure, "
    "propose it normally (it waits for him) and say what you would need. "
    "Never claim a fix you did not get an 'auto_applied' result for. "
    # 2026-09-14: thirteen notes named bonsai_llm.py line 564 and none
    # proposed anything. A diagnosis is not a deliverable.
    "A NOTE THAT NAMES A FILE AND A LINE IS UNFINISHED UNTIL propose_code_fix "
    "HAS BEEN CALLED for it -- with apply_now=true if it is small and you are "
    "sure, otherwise apply_now=false so it waits for Barry. Diagnosing the "
    "same line again next tick is not work; the proposal is.\n\n")

# SLOW REPLIES: HERS TO SOLVE (2026-09-28, Barry: "if its something she can fix, let her do it.
# she can be proactive on some things"). Tools on for this turn; the codefix gate still decides
# what may apply without him (simple OR build-broken) -- she cannot talk her way past it.
_ASK_SLOW = (
    "SLOW REPLIES IS YOURS TO SOLVE. Barry's words: \"if its something she can fix, let her "
    "do it. she can be proactive on some things.\" You have your tools for this turn. Read the "
    "evidence in the finding first. If the writing speed is healthy, the time is going on cold "
    "re-reads or heavy work: find what is stopping Bonsai (the 'STOP requested' caller names the "
    "file and line) or what made the turns heavy, and FIX it -- propose_code_fix with "
    "apply_now=true when the change is small and you are sure (the office's gate decides if it "
    "may apply without him), otherwise apply_now=false so it waits for him. Only if the writing "
    "speed has really dropped (5-17 tokens/s) is it GPU decay -- then tell him plainly a machine "
    "reboot is the fix; that one is his to do. Never tell him to reboot on a healthy speed.\n\n")

_DIAG_RE = re.compile(r"\b[\w\-]+\.py\b.{0,80}?\bline\s+\d+|\bline\s+\d+.{0,80}?\b[\w\-]+\.py\b",
                      re.IGNORECASE | re.DOTALL)
_NUDGE_PROPOSE = (
    "\n\nOFFICE CHECK: your note names a file and a line but you did NOT call "
    "propose_code_fix. That note is unfinished. Read the exact lines, then call "
    "propose_code_fix now with the verbatim snippet to replace and the "
    "replacement (apply_now=true only if it is small and you are sure), and "
    "rewrite the note to say what you proposed or applied.")
_ASK_TAIL = (
    "Now write a short WORK NOTE to Barry -- he is 'you', talk to him directly. "
    "Say what you saw, what it most likely means in plain words (he does not "
    "code -- define any technical word in the same sentence), and what you did "
    "or want to do. Be honest about what you do NOT know. Anything you did not "
    "apply is unchanged; never say you fixed, restarted or sent something you "
    "did not. If none of this is worth his attention, reply with exactly: "
    "NOTHING TO REPORT\n\nJust the note. No headings, no sign-off, no more "
    "than ~180 words.")


def _auto_fixes_since(iso: str) -> list[int]:
    with memory.get_db() as conn:
        rows = conn.execute(
            "SELECT id FROM approvals WHERE action_type='code_fix' AND "
            "dispatch_status='auto_applied' AND decided_at > ? ORDER BY id", (iso,)).fetchall()
    return [int(r["id"]) for r in rows]


async def _write_note(get_agent_fn, findings: list[str], reminders: list[str],
                      vital: list[str]) -> bool:
    import llm_router
    import reflect
    import ingest
    from agents import ENGINEER_ID

    agent = get_agent_fn(ENGINEER_ID)
    if not agent:
        return False
    office = agent["office_name"]
    system_prompt = agent["system_prompt"]
    try:
        add = ingest.persona_additions(office)
        if add:
            system_prompt += "\n\n" + add
    except Exception:
        pass

    ask = _ASK_HEAD
    if findings:
        ask += _ASK_FINDINGS.format(findings="\n".join(f"- {f}" for f in findings))
    if reminders:
        ask += _ASK_REMINDERS.format(reminders="\n".join(f"- {f}" for f in reminders))
    if vital:
        ask += _ASK_VITAL.format(vital="\n".join(f"- {v}" for v in vital))
    slow = any(f.startswith("SLOW REPLIES") for f in findings)
    if slow:
        ask += _ASK_SLOW
    ask += _ASK_TAIL

    extra_tools = None
    if vital or slow:
        extra_tools = [
            llm_router.SYSTEM_HEALTH_TOOL, llm_router.INVESTIGATE_TRACES_TOOL,
            llm_router.READ_PROJECT_FILE_TOOL, llm_router.LIST_PROJECT_DIRECTORY_TOOL,
            llm_router.PROPOSE_CODE_FIX_TOOL, llm_router.LIST_CODE_FIXES_TOOL,
            llm_router.SEARCH_PROJECT_TOOL, llm_router.RUN_COMMAND_TOOL,
        ]

    backend, model = memory.get_active_generation()
    cycle_start = _now_iso()
    tok = tracing.set_call_context("system")
    t0 = time.time()
    tool_log: list = []
    try:
        reply = await llm_router.generate(
            backend, system_prompt, [{"role": "user", "content": ask}],
            model=model, use_tools=bool(vital or slow), extra_tools=extra_tools, office_name=office,
            tool_call_log=tool_log,
        )
        # The diagnosis-without-a-proposal net (2026-09-14). One re-run,
        # with the gap in front of her; the log is the evidence, never her prose.
        if ((vital or slow) and reply and not reply.startswith("[")
                and _DIAG_RE.search(reply)
                and not any(str(c.get("name") if isinstance(c, dict) else c) == "propose_code_fix"
                            for c in tool_log)):
            _log("diagnosis named a file+line with no propose_code_fix -- re-running once")
            reply = await llm_router.generate(
                backend, system_prompt,
                [{"role": "user", "content": ask},
                 {"role": "assistant", "content": reply},
                 {"role": "user", "content": _NUDGE_PROPOSE}],
                model=model, use_tools=True, extra_tools=extra_tools, office_name=office,
                tool_call_log=tool_log,
            )
    finally:
        tracing.reset_call_context(tok)
    took = time.time() - t0

    applied = _auto_fixes_since(cycle_start)
    if not reply or reply.startswith("["):
        _log(f"note generation failed ({(reply or 'empty')[:80]})"
             + (f" -- BUT she applied fix(es) {applied} this cycle" if applied else ""))
        if not applied:
            return False
        reply = ("(My note failed to generate, but the record shows I applied fix "
                 + ", ".join(f"#{i}" for i in applied) + " this cycle. Check list_code_fixes "
                 "or ask me; undo with 'undo fix #N'.)")
    if "NOTHING TO REPORT" in reply.upper() and len(reply) < 200 and not applied:
        _log(f"Sophie: nothing to report ({took:.0f}s)")
        return True

    body, fixed = reflect._scrub_delivery_claims(reply.strip())
    if fixed:
        _log(f"corrected {fixed} invented delivery claim(s)")
    today = datetime.date.today().isoformat()
    if applied:
        # URGENT so /api/inbox lets it through after hours -- he said "tell me
        # what she did". The stamp is system text; her words are untouched.
        ids = ", ".join(f"#{i}" for i in applied)
        stamp = (f"[URGENT -- Sophie, on watch, {today} -- she applied fix {ids} herself "
                 f"because the build was failing; say 'undo fix {ids}' to put it back]\n\n{body}")
    else:
        stamp = f"[Sophie, on watch, {today}]\n\n{body}"
    reflect._store(office, f"worknote-watch-{today}.md",
                   f"Sophie has a work note from her watch -- {today}", stamp)
    _log(f"work note filed ({len(body)} chars, {took:.0f}s"
         + (f", applied {applied}" if applied else "") + f"): {body[:100]!r}")
    return True


# --- the loop -------------------------------------------------------------------

async def tick(get_agent_fn, force: bool = False) -> dict:
    """One pass. `force=True` (the manual POST /api/watch/tick) skips the
    idle gate and the repeat/gap throttles -- Barry asked for it, so he gets
    it now. Findings held from a busy pass are CARRIED into the next one:
    check() only sees what is new since last_check, so without this a
    failure that landed while he was chatting would never be reported."""
    import ideation
    st = _state()
    findings = check(st)
    carried = [f for f in (st.get("pending") or []) if f not in findings]
    findings = carried + findings
    reminders, remind_ids = pending_fix_reminders(st)
    vital = vital_conditions() if findings or force else []
    st["last_check"] = _now_iso()
    st["last_findings"] = findings
    st["last_vital"] = vital
    result = {"findings": findings, "reminders": reminders, "vital": vital,
              "noted": False, "skipped": None}

    if not findings and not reminders:
        st.pop("pending", None)
        _save(st)
        return result

    fp = _fingerprint(findings)
    last_fp = st.get("last_fingerprint")
    last_note_at = float(st.get("last_note_at") or 0)
    now = time.time()
    same_as_before = (fp == last_fp and now - last_note_at < REPEAT_SAME_FINDINGS_AFTER_SECONDS)
    vital_fp = _fingerprint(vital) if vital else ""
    same_breakage = (bool(vital) and vital_fp == st.get("last_vital_fp")
                     and now - last_note_at < VITAL_REPEAT_GAP_SECONDS)
    # A due reminder or a NEW live breakage is never throttled by "same as
    # before"; the same breakage she already wrote up waits an hour.
    if not force and same_breakage and not reminders:
        result["skipped"] = "same breakage already reported this hour -- holding"
        st["pending"] = findings
    elif not force and same_as_before and not reminders and not vital:
        result["skipped"] = "same findings already reported today"
    elif not force and not reminders and not vital and now - last_note_at < MIN_GAP_BETWEEN_NOTES_SECONDS:
        result["skipped"] = "last note too recent -- holding"
        st["pending"] = findings
    elif not force and not ideation._is_idle():
        result["skipped"] = "office busy -- holding until idle"
        st["pending"] = findings
    else:
        st.pop("pending", None)
        if await _write_note(get_agent_fn, [] if same_as_before else findings, reminders, vital):
            st["last_fingerprint"] = fp
            st["last_note_at"] = now
            st["last_vital_fp"] = vital_fp
            rem = st.get("reminded") or {}
            for i in remind_ids:
                rem[str(i)] = now
            st["reminded"] = rem
            result["noted"] = True
    if result["skipped"]:
        _log(f"{len(findings)} finding(s), {len(reminders)} reminder(s); {result['skipped']}")
    _save(st)
    return result


def status() -> dict:
    """For system_health -- so Sophie can see what her own watch last found."""
    st = _state()
    return {
        "last_check": st.get("last_check") or "never",
        "last_findings": st.get("last_findings") or [],
        "build_broken_signals": st.get("last_vital") or [],
        "holding_for_idle": st.get("pending") or [],
        "last_note_at": (datetime.datetime.fromtimestamp(st["last_note_at"]).isoformat(timespec="minutes")
                         if st.get("last_note_at") else "never"),
    }


async def run_watch_loop(get_agent_fn) -> None:
    """Background task, started in main.py's lifespan. Never crashes the loop."""
    await asyncio.sleep(STARTUP_DELAY_SECONDS)
    while True:
        try:
            await tick(get_agent_fn)
        except Exception as e:  # noqa: BLE001
            _log(f"loop error (living on): {e}")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
