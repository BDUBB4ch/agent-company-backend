"""Degradation monitor -- tells Barry when the office is slipping.

Barry, 2026-08-31: "i also want a degradation monitor. when things start to bogg
down or the agents start slipping or not fully using their brains ar skills or
not using their functions, like reasoning, logic and thinking and proper
responses... to tell me to restart or something."

This office degrades in known, measured ways, and every one of them has been
paid for at least once:

  * REPLIES GET SLOW. The GPU's memory state decays across a render marathon
    (43s/step -> 267s/step measured 2026-08-29) and only a REBOOT clears it.
    A prompt-cache break does the same thing to chat (full re-prefill, 61s to
    answer "say ok").
  * AGENTS STOP USING THEIR TOOLS. Measured repeatedly: Amara answered from
    stored text with tool_calls empty; Elliot went 23 of 25 calls with no tool
    at all. The capability is there and unused, which reads as "he got dumber".
  * REPLIES GET SHORT. The early-EOS gremlin (413 chars, natural stop) and the
    "[Agent kept searching...]" guard string.
  * BRAINS GET FAT. Elliot produced word salad at 220K always-on. Warn 140K,
    fail 190K.

So it compares a RECENT window against an EARLIER one from the same log rather
than against hardcoded numbers -- what matters is the office getting worse than
it was, not whether it hits some absolute figure.

Read-only. No model calls, no network. Safe to poll.
"""

import io
import json
import os
import statistics

_HERE = os.path.dirname(os.path.abspath(__file__))
TRACES = os.path.join(os.path.dirname(_HERE), "data", "traces.jsonl")

RECENT = 25          # calls in the "now" window
BASELINE = 75        # calls before that, used as "how it was"

# Always-on brain load. 140K is the documented warn line, 190K the fail line
# (Elliot produced word salad at 220K).
LOAD_WARN = 140_000
LOAD_FAIL = 190_000

# A STUB IS A REPLY THAT FAILED, NOT A REPLY THAT WAS SHORT.
#
# This was 200 chars and it was simply the wrong bar. Measured against real
# traffic: Victor's good answers run 300-500 chars, and plenty of correct,
# useful answers land at 150-200. Calling those a defect meant the monitor
# nagged Barry to restart a healthy backend, repeatedly, on nothing.
#
# What an actually-broken reply looks like in this build is the early-EOS
# gremlin: a few words, or 39 chars of nothing, where a real answer was asked
# for. That is what 40 catches. Truly empty replies are already caught
# separately by tracing's `no_content` failure signature.
STUB_CHARS = 40
SLOW_FACTOR = 1.8    # recent median this much worse than baseline = bogging


def _load_traces(limit=400):
    if not os.path.isfile(TRACES):
        return []
    rows = []
    with io.open(TRACES, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    # Agent calls only -- office_name None is a summarizer/vision/bench call
    # and would pollute every number here.
    rows = [r for r in rows if r.get("office_name")]
    return rows[-limit:]


def _median(xs):
    return statistics.median(xs) if xs else 0.0


# A SHORT REPLY IS ONLY A SYMPTOM IF SOMEONE ASKED A REAL QUESTION.
#
# Found 2026-08-31: this reported "76% of replies stubby -- restart the
# backend" on a backend that was completely healthy. The window it measured
# was break-room DMs, a personal-channel exchange and a handful of "say ok"
# test messages. A 120-character line in a DM is a person talking; a 3-char
# "Ok." is the CORRECT answer to "say ok". The rule predates the break room
# and the personal channel entirely.
#
# So the stub metric only counts calls that are actually work answers:
#   - context is explicitly "chat" (not social / reflection / system, and not
#     a legacy line we cannot classify), and
#   - a prompt long enough that a long answer was ever expected.
_TRIVIAL_PROMPT_CHARS = 24   # "say ok", "hi", "thanks" -- nothing was asked


def _is_work_answer(r) -> bool:
    # The context field arrived 2026-08-31. A trace WITHOUT it is from before
    # that and cannot be classified -- it may be a break-room DM, a reflection
    # or a "say ok" test. Judging it as a work answer is exactly what kept the
    # stubby banner firing after the first fix. Unclassifiable data is excluded,
    # not assumed; the metric simply has less to go on until fresh traffic lands.
    if r.get("context") != "chat":
        return False
    pc = r.get("prompt_chars")
    if pc is not None and pc < _TRIVIAL_PROMPT_CHARS:
        return False
    return True


def _window_stats(rows):
    # SLOWNESS IS MEASURED ON GENERATION, NOT ON WORK (2026-09-02). The banner
    # told Barry to REBOOT ("86s, was 43s, 2.0x worse") on an evening when the
    # slow turns were the company board working briefs -- eight web searches
    # in one turn, three-turn huddles, my own drills -- none of which is GPU
    # decay. A turn that ran tools is as long as the tools were. So the
    # median is taken over live chat answers that called NO tool, and task
    # turns (board briefs, email drafts, probes; context 'task') are out.
    judged = [r for r in rows if _is_work_answer(r)]
    # EMPTY REPLIES ARE NOT FAST ANSWERS (2026-09-28): 11 empty 0.2 s turns from a backend
    # start-up became the baseline, and a healthy 37-39 tok/s Bonsai read "395.8x worse".
    durs = [r.get("duration_ms") or 0 for r in judged
            if r.get("duration_ms") and not r.get("tool_calls")
            and (r.get("final_content") or "").strip()]
    contents = [(r.get("final_content") or "") for r in judged]
    # TOOL USE IS MEASURED ON WORK CHAT ONLY (2026-09-03). This was the one
    # rule in this file that never got the fix the other three got, and it
    # fired on Barry's screen because of it: an evening of group chat, DMs and
    # reflections -- where tools are switched OFF BY CONSTRUCTION -- was
    # compared against a working day of briefs and health checks, and the
    # difference was reported as the agents refusing to use their brains.
    # Restarting the backend cannot change a number that is 0 by design.
    # Same population as the stub rule: context 'chat', real ask, no
    # unclassifiable legacy lines.
    return {
        "calls": len(rows),
        "median_ms": round(_median(durs)) if durs else 0,
        "timed_sample": len(durs),
        "tool_rate": round(sum(1 for r in judged if r.get("tool_calls")) / len(judged), 3)
                     if judged else 0.0,
        "tool_sample": len(judged),
        # measured over WORK answers only -- see _is_work_answer
        "stub_rate": round(sum(1 for c in contents if len(c) < STUB_CHARS) / len(contents), 3)
                     if contents else 0.0,
        "stub_sample": len(contents),
        # Failures Barry would actually meet: live chat turns only. Board
        # briefs, huddles and reflections retry or report on their own
        # (teamwork.py / watch.py); a dead background run is not "the office
        # is failing" -- it fired the banner over test collisions 2026-09-02.
        "failures": sum(1 for r in rows if (r.get("context") or "chat") == "chat"
                        and (r.get("failure_signature") or r.get("error"))),
    }


def check() -> dict:
    """One read of how the office is doing, with a plain recommendation."""
    problems, notes = [], []

    rows = _load_traces()
    recent_rows = rows[-RECENT:]
    base_rows = rows[-(RECENT + BASELINE):-RECENT] if len(rows) > RECENT else []
    recent = _window_stats(recent_rows)
    base = _window_stats(base_rows)

    enough = recent["calls"] >= 8 and base["calls"] >= 8

    # --- bogging down --------------------------------------------------
    # needs a real sample on BOTH sides: a median of two turns is a coin flip
    # ROUTED TO SOPHIE (2026-09-28, Barry: "thats the type of stuff she needs to handle...
    # route it to her"). This used to be a banner telling HIM to reboot -- and it fired on a
    # healthy Bonsai. Now it is a finding on Sophie's watch (watch.check -> slowdown_finding)
    # with the evidence attached; she diagnoses and writes him a work note. No banner.
    slowdown = None
    if (enough and base["median_ms"] and recent["median_ms"]
            and recent["timed_sample"] >= 5 and base["timed_sample"] >= 5):
        ratio = recent["median_ms"] / base["median_ms"]
        if ratio >= SLOW_FACTOR:
            slowdown = {"recent_s": recent["median_ms"] / 1000, "earlier_s": base["median_ms"] / 1000,
                        "ratio": ratio, "sample": recent["timed_sample"]}
            notes.append("Plain replies are slower (%.0fs, was %.0fs) -- handed to Sophie's watch."
                         % (slowdown["recent_s"], slowdown["earlier_s"]))

    # --- not using their tools -----------------------------------------
    # Needs a real sample of WORK CHAT on both sides, not just a lot of calls.
    # Even in real chat a tool is only sometimes the right answer -- "morning,
    # Barry" is not a failure -- so a handful of turns proves nothing either
    # way, and a quiet evening proves nothing at all.
    if recent["tool_sample"] >= 8 and base["tool_sample"] >= 8:
        if recent["tool_rate"] < 0.10 and base["tool_rate"] >= 0.25:
            problems.append({
                "what": "The agents have stopped using their tools",
                "detail": "Only %d%% of the last %d work answers used a tool, down from "
                          "%d%% (chit-chat, private time and background work are not "
                          "counted -- tools are off in those by design)."
                          % (recent["tool_rate"] * 100, recent["tool_sample"],
                             base["tool_rate"] * 100),
                "do": "Restart the backend. If it keeps happening, a thread is "
                      "probably poisoned -- clear that agent's thread.",
                "severity": "medium",
            })
        elif recent["tool_rate"] == 0.0 and recent["tool_sample"] >= 12:
            notes.append("No tool was used in the last %d work answers."
                         % recent["tool_sample"])

    # --- stub answers ---------------------------------------------------
    # Needs a real SAMPLE of work answers, not just a lot of calls: an evening
    # of break-room chatter is 25 calls and zero evidence either way.
    if recent["stub_sample"] >= 8 and recent["stub_rate"] >= 0.45:
        problems.append({
            "what": "Replies are coming back stubby",
            "detail": "%d%% of the last %d work answers were under %d characters "
                      "(chit-chat and one-word asks are not counted)."
                      % (recent["stub_rate"] * 100, recent["stub_sample"], STUB_CHARS),
            "do": "Restart the backend. If one agent is doing it, clear that "
                  "agent's thread -- a bad turn in history repeats itself.",
            "severity": "medium",
        })

    # --- outright failures ----------------------------------------------
    # "Failing" means NOW, not "six things went wrong tonight and then it
    # recovered" (2026-09-02: the banner stayed up on Barry's screen over
    # test collisions that had already resolved). So: enough failures in the
    # window AND one of the last five live chat calls also failed.
    _last_chat = [r for r in recent_rows if (r.get("context") or "chat") == "chat"][-5:]
    # 2026-09-14: "one of the last five" is a COUNT window, so with no chat
    # since, three old failures sat on Barry's screen for hours after the
    # fix ("its still showing up"). A failure only counts as NOW if it is
    # also younger than 30 minutes.
    _still_failing = False
    for r in _last_chat:
        if not (r.get("failure_signature") or r.get("error")):
            continue
        try:
            import datetime as _dt
            _t = _dt.datetime.fromisoformat(str(r.get("timestamp") or "").replace("Z", "+00:00"))
            if _t.tzinfo is None:
                _t = _t.replace(tzinfo=_dt.timezone.utc)
            _age = (_dt.datetime.now(_dt.timezone.utc) - _t).total_seconds()
        except Exception:  # noqa: BLE001
            _age = 0  # unparseable timestamp: treat as current, never hide a live failure
        if _age <= 30 * 60:
            _still_failing = True
            break
    if recent["failures"] >= 3 and _still_failing:
        problems.append({
            "what": "Calls are failing outright",
            "detail": "%d failures in the last %d calls, including one of the last five."
                      % (recent["failures"], recent["calls"]),
            "do": "Ask Sophie for a health check; if Bonsai is down, restart the backend "
                  "and check data/bonsai_server.log.",
            "severity": "high",
        })
    elif recent["failures"] >= 3:
        notes.append("%d failures earlier in the window, none in the last 30 minutes "
                     "-- it recovered." % recent["failures"])

    # --- fat brains ------------------------------------------------------
    try:
        import agents
        import memory
        for aid, office, name in agents.all_seats():               # hires too (2026-10-10)
            agent = {"name": name}
            load = len(memory.brain_context_block(office))
            try:
                load += len(memory.pinned_skills_block(
                    office, agents.PINNED_SKILLS.get(aid, [])))
            except Exception:
                pass
            if load >= LOAD_FAIL:
                problems.append({
                    "what": "%s's brain is overloaded" % agent.get("name", office),
                    "detail": "%s characters always-on (fails above %s)."
                              % (f"{load:,}", f"{LOAD_FAIL:,}"),
                    "do": "Move their biggest always-on documents to on-demand "
                          "(add .md to the source name). At this size replies "
                          "turn to word salad.",
                    "severity": "high",
                })
            elif load >= LOAD_WARN:
                notes.append("%s is carrying %s characters always-on (warn line %s)."
                             % (agent.get("name", office), f"{load:,}", f"{LOAD_WARN:,}"))
    except Exception as exc:
        notes.append("Could not measure brain sizes: %s" % exc)

    # --- verdict ----------------------------------------------------------
    if any(p["severity"] == "high" for p in problems):
        status, headline = "degraded", "Something is wrong -- see below."
    elif problems:
        status, headline = "slipping", "Starting to slip."
    elif not enough:
        status, headline = "ok", "Not enough recent activity to judge yet."
    else:
        status, headline = "ok", "Running normally."

    return {
        "status": status,
        "headline": headline,
        "problems": problems,
        "notes": notes,
        "slowdown": slowdown,
        "measured": {"recent": recent, "earlier": base},
    }


# --- evidence for Sophie (2026-09-28) ------------------------------------------
_DATA = os.path.join(os.path.dirname(_HERE), "data")
_GEN_RE = __import__("re").compile(r"\|\s+eval time =\s+([\d.]+) ms /\s+(\d+) tokens")


def generation_speed(last: int = 8) -> tuple[float | None, int]:
    """Median Bonsai WRITING speed (tokens/s) over the last `last` replies of 32+ tokens,
    read from the tail of data/bonsai_server.log. ~37-40 healthy, 5-17 = real GPU decay."""
    path = os.path.join(_DATA, "bonsai_server.log")
    try:
        with open(path, "rb") as f:
            f.seek(max(0, os.path.getsize(path) - 400_000))
            tail = f.read().decode("utf-8", "replace")
    except OSError:
        return None, 0
    rates = []
    for line in tail.splitlines():
        if "prompt eval time" in line:
            continue
        m = _GEN_RE.search(line)
        if m and int(m.group(2)) >= 32 and float(m.group(1)) > 0:
            rates.append(int(m.group(2)) / (float(m.group(1)) / 1000))
    rates = rates[-last:]
    return (round(statistics.median(rates), 1) if rates else None), len(rates)


def recent_bonsai_stops(hours: float = 6) -> list[str]:
    """'STOP requested: <caller>' lines from data/bonsai_events.log in the last `hours`.
    Each stop costs the next reply a full cold re-read of its prompt."""
    import datetime as _dt
    cutoff = (_dt.datetime.now() - _dt.timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(os.path.join(_DATA, "bonsai_events.log"), encoding="utf-8", errors="replace") as f:
            return [ln.strip() for ln in f if "STOP requested" in ln and ln[:19] >= cutoff]
    except OSError:
        return []


def slowdown_finding() -> str | None:
    """One watch finding for Sophie when plain replies have slowed, with the evidence she
    needs to tell decay (reboot) from cold re-reads (something stopping Bonsai) from heavy work."""
    try:
        s = check().get("slowdown")
    except Exception:  # noqa: BLE001
        return None
    if not s:
        return None
    tps, n = generation_speed()
    stops = recent_bonsai_stops()
    speed = (f"Bonsai is writing at {tps} tokens/s over its last {n} replies (healthy ~37-40, "
             f"real GPU decay 5-17)" if tps else "Bonsai's writing speed could not be read")
    stop_txt = (f"{len(stops)} Bonsai stop(s) in the last 6h, latest: {stops[-1]}" if stops
                else "no Bonsai stops logged in the last 6h")
    return (f"SLOW REPLIES -- a tool-free chat answer now takes {s['recent_s']:.0f}s, was "
            f"{s['earlier_s']:.0f}s ({s['ratio']:.1f}x, {s['sample']} answers). {speed}. {stop_txt}. "
            f"Your skill 'slowdown-triage-2026-09-28' has how to read this.")
