"""
Bonsai provider -- Ternary Bonsai 27B served by the PrismML llama.cpp
fork's llama-server, spoken to over its OpenAI-compatible API.

Why this exists as its own module instead of another branch inside
llm_router's Ollama code: Bonsai physically cannot run under Ollama (the
ternary Q2_0 quantization only loads on the PrismML fork), so it needs its
own server process, its own lifecycle management, and its own API shape.
llm_router.generate() routes backend=="bonsai" here and passes in its own
tool dispatcher so both providers execute the exact same real tools
(search_web, read_skill, Sophie's file tools) -- the dispatcher is a
parameter rather than an import specifically to avoid a circular import
between this module and llm_router.

VRAM contract (the same only-one-thing-resident principle the rest of the
project already enforces between Ollama models and AmuseBridge): Bonsai
(~8GB incl. context) cannot share a 16GB card with any resident Ollama
model (the abliterated 9B alone runs ~8-10GB with its context window, and
phi4-reasoning:14b is ~12GB). So llm_router unloads all Ollama models
before a Bonsai call, and stops THIS server before any Ollama call --
stop_server() below is what makes that second direction possible.
"""
import asyncio
import json
import os
import re
import subprocess
import time

import httpx

import claim_net

from config import (
    BONSAI_HOST,
    BONSAI_MODEL_PATH,
    BONSAI_MMPROJ_PATH,
    BONSAI_MMPROJ_GPU,
    BONSAI_NUM_CTX,
    BONSAI_KV_TYPE,
    BONSAI_SPEC_TYPE,
    BONSAI_SERVER_EXE,
    BONSAI_MODEL_NAME,
)

# Same defensive cleanup as llm_router._clean_ollama_content -- Bonsai is a
# hybrid-reasoning model and can emit <think>...</think> blocks inline in
# content depending on the chat template. Never surface reasoning.
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

# Matches llm_router.MAX_TOOL_ROUNDS -- same reasoning: a model that keeps
# calling tools without settling on an answer shouldn't hang a chat forever.
MAX_TOOL_ROUNDS = 3
# Per-turn ceiling on tool output fed back into the prompt (chars), and the
# ceiling for any single result. ~10K tokens total leaves room for an office
# prompt (~30-35K tokens) plus the reply inside the 49,152 window.
TOOL_RESULT_BUDGET_CHARS = 40_000
# Server-wide thinking ceiling (tokens). See the launch args for the history;
# measured A/B 2026-09-15 in data/bench_reasoning_budget_2026-09-15.json.
REASONING_BUDGET = int(os.getenv("BONSAI_REASONING_BUDGET", "-1"))
# -1 (UNRESTRICTED) SINCE 2026-09-15, ON PURPOSE. A server-wide budget makes
# the server ignore every per-request one; with it unset, this fork honours
# `thinking_budget_tokens` per request (the OLD key -- `reasoning_budget_
# tokens` is ignored; measured, data/probe_per_request_budget_2026-09-15.json).
# The per-message dial below is what limits thinking now.

# PER-MESSAGE THINKING (Barry, 2026-09-15: "shorter as in the length of time
# it reasons, vs a deeper reasoning" -> "build the guard and make 1024 the
# default"). Every ordinary turn thinks up to THINK_BUDGET_DEFAULT tokens and
# is then told, inside its reasoning, to answer; a deep ask (main.py sets the
# override to -1) thinks without limit. Measured on the margin puzzle: 1024 +
# the wrap-up message = the same right answer in 19s instead of 35s; WITHOUT
# the wrap-up message the cut lands mid-thought and the rest of the reasoning
# spills into the visible answer. The spill still happens sometimes even with
# the message (2 of 5 runs), so `_looks_spilled` retries once unlimited.
THINK_BUDGET_DEFAULT = int(os.getenv("BONSAI_THINK_BUDGET", "1024"))
# The ROLE-RESET wording (2026-09-15). The old line was "Time is up -- stop
# thinking and give the final answer now." -- it said stop, not what a spill
# is, and on Amara's home turn the tail of her reasoning (third-person
# narration of Barry and the scene) came out as the visible answer. This
# names the failure. Measured against the old line: see data/think_cuts.jsonl
# and the 2026-09-15 record. The marker prefix below is what
# _budget_cut_fired looks for, so keep "Thinking budget exhausted" first.
THINK_BUDGET_MESSAGE = ("Thinking budget exhausted. Stop all internal narration now. Do not "
                        "continue any third-person description of Barry or of the scene. "
                        "Write only the reply, as yourself, directly to Barry in second "
                        "person -- 'you' is Barry.")
# Every character an agent works beside; a leaked-narration paragraph that
# names one of them is NOT stripped (it may be a real sentence about a
# coworker), it is retried instead. Duplicated from reflect.HUMAN_NAMES on
# purpose -- importing reflect here would be circular.
_COWORKER_NAMES_RE = re.compile(
    r"\b(?:Victor|Priya|Amara|Marcus|Derek|Vivian|Elliot|Sophie|Taliyah)\b")
# think_budget_override (the per-request ContextVar) is defined next to max_tokens_override below.
TOOL_RESULT_MAX_CHARS = 14_000
# 2026-09-06: a per-request override. Sophie's build asks need to search and
# read several files before she can plan -- measured: five tool calls in
# three rounds and the reply was a one-line "Let me read memory.py". main.py
# sets this to a larger budget for her chat turns; everyone else keeps 3.
import contextvars as _cv
tool_rounds_override: _cv.ContextVar[int | None] = _cv.ContextVar("tool_rounds_override", default=None)

# QUICK REPLIES (2026-09-08, Barry: "build the reasoning budget thing for
# short messages"). Measured on a warm turn: 2.9s prefill, then 69s
# generating ~3K tokens of reasoning to answer "cool, ill grab some row cover"
# in two sentences. The fork's --reasoning-budget is SERVER-WIDE: per-request
# `reasoning_budget`, `thinking_budget` and `reasoning.max_tokens` were all
# probed and ignored (budget 150 still reasoned 2,280 chars); a "think
# briefly" line in the USER turn did nothing; the same line in the SYSTEM
# prompt halved reasoning; `chat_template_kwargs.enable_thinking=false` is the
# only hard stop. So a short casual message gets (1) the static depth rule in
# agents.py, (2) a max_tokens CAP set here by main.py, and (3) if the cap
# swallows the answer (reasoning ran to the cap, content empty), ONE retry
# with thinking off -- a fallback, never the norm, so thinking stays on.
max_tokens_override: _cv.ContextVar[int | None] = _cv.ContextVar("max_tokens_override", default=None)
quick_reply: _cv.ContextVar[bool] = _cv.ContextVar("quick_reply", default=False)
# 4096 -> 6144 (2026-09-19). The reply ceiling is shared with reasoning, so a
# long-form ask -- "describe yourself in great detail AND give me the prompt" --
# spends ~1,024 tokens thinking and then runs out mid-answer. Measured on
# ilnora: two turns ended at EXACTLY 4096, which is a ceiling, never a
# coincidence. Cheap: a turn that finishes naturally never touches this, so
# only the turns that were being truncated change, and the worst case a
# runaway can cost goes 4096 -> 6144 tokens (~70s more at 30 tok/s). Elliot's
# shot asks have run at 6144 over a ~42K-token prompt since 2026-09-14, so the
# window has the room. Env override if it ever needs pulling back.
DEFAULT_MAX_TOKENS = int(os.getenv("BONSAI_MAX_TOKENS", "6144"))


# PER-SEAT SAMPLING (2026-10-17, Barry: "they all kinda talk the same"). One model, one server-wide temperature =
# one rhythm for ten people. Each seat now sends its own sampling with every request (llama-server honours
# per-request fields; anything not listed falls back to the server's launch settings). Small, deliberate nudges:
# tighter = clipped and exact, looser = more expressive. Keys are office_name. Measured by
# scripts/voice_distance_2026_10_17.py (before/after). Tools, not seeds: this is mechanics, not who they are.
SEAT_SAMPLING: dict[str, dict] = {
    "Operations":    {"temperature": 0.8,  "presence_penalty": 1.2},   # Priya: clipped, no repeats
    "Legal":         {"temperature": 0.7,  "top_p": 0.9},              # Marcus: flat, precise
    "Engineer":      {"temperature": 0.75},                             # Sophie: exact
    "CIO":           {"temperature": 0.85},                             # Victor: steady
    "Marketing":     {"temperature": 0.95},                             # Derek: plain, a little lift
    "ilnora":        {"temperature": 0.9},                              # Ilnora: unhurried
    "Creative":      {"temperature": 1.05},                             # Vivian: sharper turns
    "BusinessOps":   {"temperature": 1.1,  "presence_penalty": 0.8},   # Amara: loose, expressive
    "MovieDirector": {"temperature": 1.1},                              # Elliot: paints
    "Taliyah":       {"temperature": 1.0},                              # as she was
}


def seat_sampling(office_name: str | None) -> dict:
    return dict(SEAT_SAMPLING.get(office_name or "", {}))


def max_tokens() -> int:
    v = max_tokens_override.get()
    return v if v and v > 0 else DEFAULT_MAX_TOKENS


# None = the default budget; -1 or 0 = unlimited; N > 0 = that many tokens.
think_budget_override: _cv.ContextVar[int | None] = _cv.ContextVar("think_budget_override", default=None)
# 2026-10-07 (Barry: "we fix"): the reasoning-loop net (A: verbatim repeat, B: dithering) fired on every one of
# Ilnora's script drafts tonight -- a 12-part video written in reasoning repeats its own JSON scaffolding
# ("show"/"shot"/"motion" on every part) and she recounts words ("wait, let me recount"), so the net cut her off and
# she "answered from notes" with an outline three times. False for a turn that is actually drafting a video.
loop_guard: _cv.ContextVar[bool] = _cv.ContextVar("loop_guard", default=True)
# GRAMMAR LOCK (2026-10-07, Barry: "build both, the grammar lock and the sections"): a JSON schema the reply MUST
# match (llama.cpp response_format). The pass runs with thinking off and no tools. Used by video_queue's section
# writer so a script can only come back as a script -- never "I've written it to ~1,747 words".
json_schema_override: _cv.ContextVar[dict | None] = _cv.ContextVar("json_schema_override", default=None)


def think_budget() -> int:
    v = think_budget_override.get()
    return THINK_BUDGET_DEFAULT if v is None else int(v)


def _think_fields(budget: int | None = None) -> dict:
    """Request-body fields for the per-message thinking budget (empty = unlimited)."""
    b = think_budget() if budget is None else budget
    if b and b > 0:
        return {"thinking_budget_tokens": int(b), "thinking_budget_message": THINK_BUDGET_MESSAGE}
    return {}


# The leading class takes an opening QUOTE as well (2026-09-19). Ilnora's first
# real answer was published as ' " is context. So the deliverable is...' -- the
# tail of her reasoning, cut mid-quotation, which the old class walked straight
# past because it only skipped whitespace and markdown. A quote followed by a
# CAPITAL is still a normal reply (Elliot opens with a line of dialogue), so
# only quote-then-lowercase/punctuation counts.
_SPILL_START_RE = re.compile(r"^[\s*#_>\-\"'“”‘’«(\[]*(?:[:,;)\]]|[a-z])")
_SPILL_PHRASE_RE = re.compile(
    r"\b(?:Wait,|wait,\s+let|But wait|Let me re-?(?:check|calculate|read|think)|Let'?s (?:calculate|verify|check|recompute)|"
    # "auto-context" is the office's own internal label for the block we staple
    # onto the user turn. It has no business in anything he reads, so a reply
    # quoting it is leaking the prompt's plumbing by definition.
    r"auto-context|step-by-step:|Time is up|stop thinking)", re.I)


def _looks_spilled(content: str) -> bool:
    """Reasoning that leaked into the visible answer after a budget cut.
    Conservative: a normal answer starts with a capital letter or a symbol
    like $ or a digit, and does not open by second-guessing itself."""
    c = (content or "").strip()
    if not c:
        return False
    head = c[:220]
    return bool(_SPILL_START_RE.match(c)) or bool(_SPILL_PHRASE_RE.search(head))


_THIRD_PERSON_RE = re.compile(r"\b(?:he|him|his|he's|he'd|he'll)\b", re.I)


def _budget_cut_fired(message: dict, budget: int | None) -> bool:
    """Did the server cut the thinking at the budget?

    MEASURED 2026-09-15: the wrap-up message is injected into the model's
    context SERVER-SIDE and never comes back in reasoning_content (nor in
    content) -- a marker test read "no cut" on ten runs the server log shows
    as "budget exhausted, forcing end sequence". The client-side signal is
    LENGTH: reasoning that stopped exactly at the budget was cut. Streamed
    rounds count one delta per reasoning token (reasoning_deltas); the
    non-streaming fallback has only characters, ~4 per token, so it uses a
    conservative floor."""
    if not budget or budget <= 0:
        return False
    n = message.get("reasoning_deltas")
    if isinstance(n, int) and n > 0:
        return n >= budget - 4
    return len(message.get("reasoning_content") or "") >= budget * 3


def _looks_spilled_after_cut(content: str) -> bool:
    """The spill shape the head-of-text test misses (Amara, 2026-09-15, a home
    turn): a first paragraph NARRATING Barry in the third person ("He's got
    the screen on the yachts... but he's here") -- the tail of her reasoning,
    capitalised and fluent -- followed by the real answer addressed to "you".
    Every reply in this office is addressed to Barry, so a narrated opening
    plus an addressed continuation is the leak. Only consulted when the cut
    is known to have fired, so a work reply that legitimately opens with
    "He ordered..." about a customer costs at most one slower retry."""
    c = (content or "").strip()
    paras = [p for p in re.split(r"\n\s*\n", c) if p.strip()]
    if len(paras) < 2:
        return False
    return bool(_THIRD_PERSON_RE.search(paras[0])) and bool(
        re.search(r"\byou\b", " ".join(paras[1:]), re.I))


def _strip_narration(content: str) -> tuple[str, str] | None:
    """THE SURGICAL STRIP (2026-09-15). Drop the leading paragraph(s) that
    narrate in the third person, up to the first paragraph that addresses
    "you". Returns (kept, dropped), or None when stripping is not safe:
    nothing would be left, the paragraphs to drop name a coworker (a real
    sentence about Marcus is not leaked reasoning) or carry a quoted line.
    None means the caller retries unlimited instead -- the slower, safer
    path, which used to be the only path."""
    c = (content or "").strip()
    paras = [p for p in re.split(r"\n\s*\n", c) if p.strip()]
    if len(paras) < 2:
        return None
    first_you = next((i for i, p in enumerate(paras) if re.search(r"\byou\b", p, re.I)), None)
    if not first_you:                       # None or 0: nothing to strip
        return None
    dropped = paras[:first_you]
    if not any(_THIRD_PERSON_RE.search(p) for p in dropped):
        return None
    for p in dropped:
        if _COWORKER_NAMES_RE.search(p) or '"' in p or "“" in p:
            return None
    return "\n\n".join(paras[first_you:]).strip(), "\n\n".join(dropped)


_CUT_LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "think_cuts.jsonl")


def _log_cut(office_name: str, message: dict, content: str, action: str,
             dropped: str | None, why: str = "") -> None:
    """Every budget cut, with the reasoning tail and what the office did
    about it (clean / strip / retry) -- the tuning data the detector lacked."""
    try:
        import json as _json
        import datetime as _dt
        rec = {"ts": _dt.datetime.now().isoformat(timespec="seconds"),
               "office": office_name, "action": action, "why": why,
               "reasoning_tail": (message.get("reasoning_content") or "")[-600:],
               "content_head": (content or "")[:400],
               "dropped": dropped}
        with open(_CUT_LOG, "a", encoding="utf-8") as f:
            f.write(_json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 -- logging must never cost a reply
        pass


def tool_rounds() -> int:
    v = tool_rounds_override.get()
    return int(v) if v else MAX_TOOL_ROUNDS

# The llama-server process THIS backend started (None if not started by us
# or already stopped). Held so stop_server() can terminate it directly
# instead of hunting processes by name.
_server_proc: subprocess.Popen | None = None

# Circuit breaker -- real incident (2026-07-29): with the dropdown left on
# Bonsai, EVERY message paid the full start-server(~20s) -> empty-reply ->
# fallback-to-Ollama cycle, which read as "the abliterated model is slow"
# when the model itself was fine. After this many consecutive Bonsai
# failures, ensure_running() refuses immediately (fallback fires with no
# server-start cost) until the backend restarts or a success resets it.
_FAILURE_TRIP_THRESHOLD = 2
_consecutive_failures = 0

# ONE STARTER, ONE STOPPER (2026-09-17). Guards start AND stop together --
# see ensure_running's docstring for the measurement that forced it. Anything
# inside the lock must use the _locked helpers or it deadlocks on itself.
_gpu_lock = asyncio.Lock()
# 2026-09-06: a tripped breaker RESETS BY TIME now. Measured that day: two
# failures at ~14:40 UTC (a GPU collision) tripped it, and since nothing but
# a restart ever reset it, EVERY call for the next two hours -- Sophie's
# watch, reflections, live chat -- fell back to the 9b while the server log
# showed Bonsai perfectly able to run. After this many seconds tripped, the
# next call gets ONE real attempt; success clears it, failure re-trips it
# for another window. A stale trip must never outlive the fault it saw.
_TRIP_RESET_SECONDS = 600
_tripped_at: float | None = None

# True once THIS backend process ever launched (or found) a Bonsai server --
# gates the zombie sweep in stop_server() so the common case (Bonsai never
# touched, every chat message calls stop_server as VRAM hygiene) costs
# nothing beyond one fast is_available() connection-refused.
_bonsai_was_used = False


_EVENTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "bonsai_events.log"
)


def event(msg: str) -> None:
    """Write one line about Bonsai's health to data/bonsai_events.log.

    2026-09-17: every one of these used to be a bare print(), and the backend's
    stdout is not captured anywhere -- `grep -c '\\[bonsai\\]' data/backend.log`
    returned ZERO. So the breaker could trip and put nine seats on the 9b with
    no record of it having happened, which is precisely why "the 27B returns
    empty responses" kept coming back as a mystery. Sophie reads this through
    system_health now. Never raises: diagnostics must not break generation.
    """
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(f"[bonsai] {msg}")
    try:
        os.makedirs(os.path.dirname(_EVENTS_PATH), exist_ok=True)
        if os.path.exists(_EVENTS_PATH) and os.path.getsize(_EVENTS_PATH) > 1_000_000:
            os.replace(_EVENTS_PATH, _EVENTS_PATH + ".1")
        with open(_EVENTS_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


class EmptyReply(RuntimeError):
    """Bonsai answered with nothing (2026-09-19).

    Raised so the router's Ollama fallback actually answers instead of
    handing Barry an empty message. Deliberately its OWN type: the server is
    healthy in this case -- one seat reasoned past its reply ceiling -- so it
    must NOT count toward the circuit breaker, exactly like the 4xx rule
    (2026-09-11). One agent's runaway thinking must never take Bonsai away
    from the other nine.
    """


class BreakerOpen(RuntimeError):
    """The breaker is tripped, so this request was refused without trying
    Bonsai (2026-09-28). Its OWN type because it must NOT count as a failure:
    counting the refusal re-armed the 600s window on every call, and two
    timeouts at 09:31/09:55 kept the whole office on fallback models until
    10:47 while the server was healthy (Barry: "I need them to be totally
    reliable").
    """


def record_failure(reason: str = ""):
    global _consecutive_failures, _tripped_at
    _consecutive_failures += 1
    event(f"failure {_consecutive_failures}/{_FAILURE_TRIP_THRESHOLD}"
          + (f" -- {reason}" if reason else ""))
    if _consecutive_failures >= _FAILURE_TRIP_THRESHOLD:
        _tripped_at = time.time()
        event(f"circuit TRIPPED after {_consecutive_failures} failures -- "
              f"every seat falls back to Ollama; retries once after {_TRIP_RESET_SECONDS}s")


def record_success():
    global _consecutive_failures, _tripped_at
    _consecutive_failures = 0
    _tripped_at = None


def is_tripped() -> bool:
    global _consecutive_failures, _tripped_at
    if _consecutive_failures < _FAILURE_TRIP_THRESHOLD:
        return False
    if _tripped_at is not None and time.time() - _tripped_at >= _TRIP_RESET_SECONDS:
        # One probe: drop to threshold-1 so the next attempt runs; a failure
        # re-trips immediately, a success clears everything.
        _consecutive_failures = _FAILURE_TRIP_THRESHOLD - 1
        _tripped_at = None
        event("circuit reset window reached -- trying Bonsai again")
        return False
    return True

# Where llama-server's own stdout/stderr goes -- real logs beat a silent
# DEVNULL when a load fails (wrong path, VRAM, driver).
_SERVER_LOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "bonsai_server.log"
)

# First-ever load on a machine can include Vulkan shader compilation on top
# of reading ~7.5GB off disk -- measured ~15s warm, so 120s is generous
# headroom, not an expected wait.
_STARTUP_TIMEOUT_SECONDS = 120

# Same rationale as llm_router's 300s Ollama timeout: give a long
# generation room to finish rather than hard-crashing the request.
_REQUEST_TIMEOUT_SECONDS = 300.0
# Once a tool turn has run this long, no more tool rounds -- it answers from
# what it gathered (2026-09-28). Well under the timeout on purpose: the final
# synthesis still has to fit inside one 300s read.
TURN_TIME_CEILING_SECONDS = 360


def _scaled(base: float) -> float:
    """A turn given a BIGGER reply cap gets a read timeout / turn ceiling that fits it (2026-10-07: Ilnora's video
    turns got a 16,384-token cap; at ~45 tok/s that is ~6 min, the 300 s read timed out and fell back to the 9b)."""
    extra = max(0, max_tokens() - DEFAULT_MAX_TOKENS)
    return base + extra / 25.0

# Sent as the last user turn when an agent exhausts its tool rounds still
# asking for more tools -- the forced-synthesis pass (2026-08-16). Shared
# with llm_router's Ollama path (imported there; defining it here avoids a
# circular import, since llm_router imports this module).
_STUB_RE = re.compile(r"^\s*(?:let me|i(?:'ll| will| am going to| need to)\s+(?:now\s+)?(?:read|look|check|open|search|inspect|examine|run))\b", re.I)


def _looks_like_stub(text: str) -> bool:
    t = (text or "").strip()
    return (not t) or len(t) < 220 and bool(_STUB_RE.match(t))


OUT_OF_ROUNDS_NUDGE = (
    "[System: you are out of tool calls for this turn. Stop searching and "
    "give Barry your best final answer RIGHT NOW from what you have already "
    "gathered above. If something important is still unverified, say what "
    "it is and how you would confirm it -- but answer the question first.]"
)


# Bonsai sometimes writes tool calls as TEXT instead of structured
# tool_calls -- the long-documented latent gap, first seen live 2026-08-16
# when raw `<tool_call><function=search_web>...` XML reached Barry as if it
# were an answer. Shape observed (Qwen/ChatML style):
#   <tool_call>\n<function=NAME>\n<parameter=KEY>\nVALUE\n</parameter>...
_PSEUDO_XML_CALL_RE = re.compile(
    r"<tool_call>\s*<function=([\w\-]+)>(.*?)(?:</function>)?\s*</tool_call>",
    re.S)
_PSEUDO_XML_PARAM_RE = re.compile(
    r"<parameter=([\w\-]+)>\s*(.*?)\s*</parameter>", re.S)


# --- LIVE REASONING ----------------------------------------------------------
# Barry, 2026-08-31: "i would like to see their reasonong, while i wait for
# their responses."
#
# THE REASONING ALREADY EXISTED AND WAS BEING THROWN AWAY. This fork emits the
# model's thinking as a SEPARATE `reasoning_content` field (not <think> inside
# content -- verified against the live server), and the non-streaming path
# simply dropped it. So this does not make the agents think; it stops hiding
# the thinking they were already doing.
#
# Kept in memory only, newest-per-agent, never written to a fact or a thread --
# it is a window, not a record. recall.py and the brain never see it.
_LIVE_THINKING: dict = {}
_LIVE_CAP = 6000


def live_thinking(office_name: str) -> dict:
    return _LIVE_THINKING.get(office_name) or {"text": "", "done": True, "chars": 0}


def _think_begin(office_name: str) -> None:
    if office_name:
        _LIVE_THINKING[office_name] = {"text": "", "done": False, "chars": 0}


def _think_push(office_name: str, piece: str) -> None:
    if not office_name or not piece:
        return
    st = _LIVE_THINKING.get(office_name)
    if st is None:
        return
    st["text"] = (st["text"] + piece)[-_LIVE_CAP:]
    st["chars"] += len(piece)


def _think_end(office_name: str) -> None:
    st = _LIVE_THINKING.get(office_name)
    if st is not None:
        st["done"] = True


# THE LOOP STOPPER (2026-09-22, Barry: "is there nothing for them to
# rationalize that they are thinking too much or have bypassed the answers
# already"). The model has no internal "you already had it" signal -- it keeps
# writing "wait, let me re-check..." and every token costs real seconds on this
# card. BeeLlama ships a reasoning-loop detector; this is ours, on the office
# side, no engine change. Two signals, both conservative on purpose (a false
# stop throws away real thinking):
#   A. a sustained VERBATIM repeat -- the last 480 chars of reasoning already
#      appeared earlier in the same reasoning (two back-to-back 240-char
#      windows both found), i.e. it is writing the same passage again;
#   B. DITHERING -- 7+ second-guessing openers in the last ~2,500 chars.
# On a hit the stream is closed (the server stops generating) and the turn is
# finished with thinking OFF, carrying the reasoning so far as notes, so the
# work already done is not thrown away.
LOOP_MIN_CHARS = 1500
LOOP_CHECK_EVERY = 300
_LOOP_WIN = 240
_DITHER_RE = re.compile(
    r"(?i)\b(?:wait[,.!]|hmm+[,.]|actually,|let me (?:re-?check|double[- ]check|"
    r"re-?read|reconsider|verify|re-?examine|go back)|on second thought|"
    r"but wait|no, wait|hold on)")


def _reasoning_loop(text: str) -> str | None:
    """Return why the reasoning looks stuck, or None. Pure, cheap."""
    if len(text) < LOOP_MIN_CHARS:
        return None
    t = re.sub(r"\s+", " ", text)
    # A: of the last 1,200 chars, cut into 100-char pieces, how many were
    # ALREADY written earlier in this same reasoning? 8 of 12 = it is copying
    # itself, whatever the length of the repeated passage.
    tail_start = len(t) - 1200
    if tail_start > 300:
        seen = sum(1 for i in range(tail_start, len(t) - 99, 100)
                   if t[i:i + 100] in t[:i])
        if seen >= 8:
            return "repeating a passage verbatim"
    if len(_DITHER_RE.findall(t[-2500:])) >= 7 and _repeat_share(t[-2500:]) >= DITHER_MIN_REPEAT:
        return "second-guessing in circles"
    return None


# DITHERING MUST ALSO REPEAT (2026-10-10, Barry: "look into the loop-stop on her seat"). data/loop_cuts.jsonl held
# 308 "second-guessing" cuts since 09-28 (107 Sophie, 142 Ilnora): Qwen writes "Actually," / "Hmm," / "Wait," as
# plain connectives, so 7 of them in 2,500 chars fired on productive reasoning -- Sophie cut at 2.4-3.9K chars while
# planning which files to read, then told "your thinking was going in circles" and answered thinking-OFF (stubby).
# Measured on those tails: a typical cut re-used 1-3% of its own 5-word phrases; the real loops (re-quoting the same
# note/regex again and again) 25-53%; 21 of 308 reach 15%. So dither words alone no longer cut -- the tail must also
# be re-saying itself.
DITHER_MIN_REPEAT = 0.15


def _repeat_share(t: str) -> float:
    """Share of the last ~45% of this text's 5-word phrases that already appeared earlier in it."""
    w = re.findall(r"[a-z0-9']+", t.lower())
    if len(w) < 200:
        return 0.0
    grams = [" ".join(w[i:i + 5]) for i in range(len(w) - 4)]
    cut = len(grams) - int(len(grams) * 0.45)
    early = set(grams[:cut])
    late = grams[cut:]
    return sum(g in early for g in late) / max(1, len(late))


async def _stream_round(client, request_body: dict, office_name: str) -> dict:
    """Run one round STREAMED, filling the live-thinking buffer as it goes.

    Returns the same `message` dict shape the non-streaming path returns, so
    the tool loop above is completely unaware this happened.

    Any failure here is raised to the caller, which falls straight back to the
    proven non-streaming request -- watching them think must never be able to
    cost Barry an answer.
    """
    body = dict(request_body)
    body["stream"] = True
    content, reasoning = "", ""
    reasoning_deltas = 0          # ~one per reasoning token; the cut signal
    tool_calls: list = []
    finish_reason = None
    loop_why, _next_check = None, LOOP_MIN_CHARS
    _think_begin(office_name)
    try:
        async with client.stream("POST", f"{BONSAI_HOST}/v1/chat/completions",
                                 json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                payload = line[6:].strip()
                if payload == "[DONE]":
                    break
                try:
                    d = json.loads(payload)
                except Exception:
                    continue
                choices = d.get("choices") or []
                if not choices:
                    continue
                if choices[0].get("finish_reason"):
                    finish_reason = choices[0]["finish_reason"]
                delta = choices[0].get("delta") or {}
                rc = delta.get("reasoning_content")
                if rc:
                    reasoning += rc
                    reasoning_deltas += 1
                    _think_push(office_name, rc)
                    if not content and len(reasoning) >= _next_check:
                        _next_check = len(reasoning) + LOOP_CHECK_EVERY
                        loop_why = _reasoning_loop(reasoning) if loop_guard.get() else None
                        if loop_why:
                            break   # closing the stream stops the server generating
                c = delta.get("content")
                if c:
                    content += c
                tc = delta.get("tool_calls")
                if tc:
                    # streamed tool calls arrive in indexed fragments
                    for frag in tc:
                        idx = frag.get("index", 0)
                        while len(tool_calls) <= idx:
                            tool_calls.append({"id": "", "type": "function",
                                               "function": {"name": "", "arguments": ""}})
                        slot = tool_calls[idx]
                        if frag.get("id"):
                            slot["id"] = frag["id"]
                        fn = frag.get("function") or {}
                        if fn.get("name"):
                            slot["function"]["name"] += fn["name"]
                        if fn.get("arguments"):
                            slot["function"]["arguments"] += fn["arguments"]
    finally:
        _think_end(office_name)
    msg = {"role": "assistant", "content": content}
    if finish_reason:
        msg["finish_reason"] = finish_reason   # "length" = hit max_tokens
    if reasoning:
        msg["reasoning_content"] = reasoning
        msg["reasoning_deltas"] = reasoning_deltas
    if tool_calls:
        msg["tool_calls"] = tool_calls
    if loop_why:
        msg["loop_cut"] = loop_why
    return msg


async def _finish_after_loop(client, request_body: dict, message: dict,
                             office_name: str) -> dict:
    """Reasoning was stopped for looping: finish the turn with thinking OFF,
    handing the model its own notes so the conclusions it reached survive."""
    notes = (message.get("reasoning_content") or "")[-6000:]
    why = message.get("loop_cut")
    print(f"[loop-stop] {office_name}: reasoning stopped ({why}) after "
          f"{len(message.get('reasoning_content') or '')} chars -- answering from its notes")
    event(f"LOOP STOP {office_name}: {why}")
    # THE EVIDENCE (2026-09-28). 68 stops in a week, 42 on Sophie, and nothing
    # recorded what she was thinking when it cut -- so a real loop and a false
    # alarm on "let me re-read the log" looked identical. Every cut keeps its
    # reasoning tail and the phrases that fired, for review before any
    # threshold changes. Never in a prompt; append-only.
    try:
        _rs = message.get("reasoning_content") or ""
        _tail = re.sub(r"\s+", " ", _rs)[-2500:]
        with open(os.path.join(os.path.dirname(_EVENTS_PATH), "loop_cuts.jsonl"), "a", encoding="utf-8") as _f:
            _f.write(json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "office": office_name,
                                 "why": why, "reasoning_chars": len(_rs),
                                 "fired": _DITHER_RE.findall(_tail), "tail": _tail}) + "\n")
    except Exception:  # noqa: BLE001 -- diagnostics never break a turn
        pass
    retry = {k: v for k, v in request_body.items()
             if k not in ("thinking_budget_tokens", "thinking_budget_message")}
    retry["chat_template_kwargs"] = {"enable_thinking": False}
    retry["messages"] = list(request_body.get("messages") or []) + [{
        "role": "user",
        "content": ("[OFFICE NOTE] Your thinking was going in circles, so it was "
                    "stopped. Your notes so far are below. You have already worked "
                    "this out -- do not re-derive it. Answer the message above now, "
                    "directly, as your normal reply.\n\nYOUR NOTES:\n" + notes)}]
    try:
        return await _stream_round(client, retry, office_name)
    except Exception:
        resp = await client.post(f"{BONSAI_HOST}/v1/chat/completions", json=retry)
        resp.raise_for_status()
        ch = resp.json().get("choices") or []
        return (ch[0].get("message") or {}) if ch else {}


def _parse_pseudo_xml_calls(content: str, valid_names: set) -> list[dict]:
    """Text-shaped tool calls -> the same dict shape the structured path
    uses, so the dispatch loop below treats them identically. Unknown tool
    names are skipped (never dispatched off a hallucinated name)."""
    calls = []
    for m in _PSEUDO_XML_CALL_RE.finditer(content or ""):
        name = m.group(1)
        if name not in valid_names:
            continue
        args = {pm.group(1): pm.group(2).strip()
                for pm in _PSEUDO_XML_PARAM_RE.finditer(m.group(2))}
        calls.append({"id": "", "function": {"name": name, "arguments": args}})
    return calls


# ...and sometimes it writes the call as a bare PYTHON-STYLE CALL instead.
# Seen live 2026-08-31: Amara's entire reply to Barry was the seven characters
#   read_skill("standing-rule")
# printed as if it were an answer. The XML parser above did not match it, so
# nothing executed it and nothing stripped it. Same class of failure as the
# 2026-08-16 XML leak, different syntax.
#
# Anchored to a WHOLE LINE on purpose: prose that merely mentions a tool by
# name ("use read_skill for that") must not be dispatched. Combined with the
# valid_names gate, only a line that is nothing but a call to a real tool runs.
_PSEUDO_PLAIN_CALL_RE = re.compile(
    r"^[ \t>*-]*([a-z_][a-z0-9_]*)\(\s*(.*?)\s*\)[ \t.;]*$", re.M | re.I)
_PSEUDO_PLAIN_KWARG_RE = re.compile(
    r"""([a-z_][a-z0-9_]*)\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
_PSEUDO_PLAIN_POSARG_RE = re.compile(r"""^(?:"([^"]*)"|'([^']*)')$""")


def _first_param_names(tools: list) -> dict:
    """tool name -> its first declared parameter, so a positional call like
    read_skill("x") can be mapped to {"topic": "x"}."""
    out = {}
    for t in tools or []:
        fn = t.get("function", {})
        props = (fn.get("parameters") or {}).get("properties") or {}
        out[fn.get("name")] = next(iter(props), None)
    return out


def _parse_pseudo_plain_calls(content: str, tools: list) -> list[dict]:
    first_param = _first_param_names(tools)
    calls = []
    for m in _PSEUDO_PLAIN_CALL_RE.finditer(content or ""):
        name, raw = m.group(1), m.group(2)
        if name not in first_param:
            continue
        # findall yields "" (not None) for the group that did not participate,
        # so pick whichever of the two quote styles actually captured text.
        args = {k: (dq if dq else sq)
                for k, dq, sq in _PSEUDO_PLAIN_KWARG_RE.findall(raw)}
        if not args and raw:
            pos = _PSEUDO_PLAIN_POSARG_RE.match(raw)
            key = first_param.get(name)
            if pos and key:
                args = {key: pos.group(1) if pos.group(1) is not None else pos.group(2)}
            elif not pos:
                continue      # unparseable arguments -- don't guess
        calls.append({"id": "", "function": {"name": name, "arguments": args}})
    return calls



def _parse_pseudo_json_calls(content: str, valid_names: set) -> list[dict]:
    """...and a THIRD shape (2026-10-10): bare JSON objects {"name": "read_project_file", "arguments": {...}}, one
    after another. Sophie's training-brief turn came back as two of them and nothing ran -- the raw JSON was her
    whole reply (1 in 381 of her replies since 09-24). Same gate as the others: only real tool names run."""
    calls, dec, i, text = [], json.JSONDecoder(), 0, content or ""
    while True:
        j = text.find("{", i)
        if j < 0:
            break
        try:
            obj, end = dec.raw_decode(text, j)
        except ValueError:
            i = j + 1
            continue
        i = end
        if isinstance(obj, dict) and obj.get("name") in valid_names and isinstance(obj.get("arguments", {}), dict):
            calls.append({"id": "", "function": {"name": obj["name"], "arguments": obj.get("arguments") or {}}})
    return calls

PIXEL_MAX_EDGE = int(os.getenv("BONSAI_PIXEL_MAX_EDGE", "1024"))
PIXEL_MAX_IMAGES = int(os.getenv("BONSAI_PIXEL_MAX_IMAGES", "3"))


def _pixel_parts(paths: list[str]) -> list[dict]:
    """Real images for the agent's own model (OpenAI image_url parts). Only when
    the server runs with the vision projector; downscaled to PIXEL_MAX_EDGE so a
    picture costs ~1K tokens, not the whole window. Failures drop that picture,
    never the turn."""
    if not os.path.isfile(BONSAI_MMPROJ_PATH):
        return []
    import base64, io
    try:
        from PIL import Image
    except Exception:
        return []
    out: list[dict] = []
    for p in list(dict.fromkeys(paths))[:PIXEL_MAX_IMAGES]:
        try:
            with Image.open(p) as im:
                im = im.convert("RGB")
                im.thumbnail((PIXEL_MAX_EDGE, PIXEL_MAX_EDGE))
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=90)
            out.append({"type": "image_url", "image_url": {
                "url": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()}})
        except Exception as exc:                   # noqa: BLE001
            print(f"[vision] could not attach {p}: {exc}", flush=True)
    return out


def _clean_content(content: str, tools: list | None = None) -> str:
    cleaned = _THINK_BLOCK_RE.sub("", content or "")
    if "</think>" in cleaned:
        cleaned = cleaned.rsplit("</think>", 1)[-1]
    # Belt for every return path: whatever pseudo-tool-call markup survives
    # to this point was NOT executed, so showing it would present dead
    # syntax as an answer. Strip it; if nothing else remains, the caller's
    # empty-content handling takes over.
    cleaned = _PSEUDO_XML_CALL_RE.sub("", cleaned)
    if tools:
        known = set(_first_param_names(tools))
        cleaned = _PSEUDO_PLAIN_CALL_RE.sub(
            lambda m: "" if m.group(1) in known else m.group(0), cleaned)
    return cleaned.strip()


async def prewarm(system_prompt: str, tools: list[dict] | None = None) -> bool:
    """Rebuild the server's prompt cache for one agent, off the clock.

    WHY (2026-08-16, Barry: Elliot's "responses are seriously slow"): the
    server log shows the real cost is the 52-55s full prefill of a ~45K-token
    agent prompt, paid on the FIRST message after anything stopped the server
    or evicted the cache -- and every image/video render stops it (VRAM
    rule). This replays the agent's prompt with max_tokens=1 in the
    background right after a render finishes, so the cache is rebuilt while
    Barry is still looking at the result and his next message lands warm.
    Best-effort by design: any failure just means the next message pays the
    old price."""
    try:
        if not await ensure_running():
            return False
        body = {
            "model": BONSAI_MODEL_NAME,
            "messages": [{"role": "system", "content": system_prompt},
                         {"role": "user", "content": "."}],
            "stream": False,
            "cache_prompt": True,
            # 8, not 1: with server-side reasoning enabled a 1-token
            # budget can abort mid-reasoning and 500. The cost of the
            # extra tokens is nothing; the prefill is the point.
            "max_tokens": 8,
        }
        # TOOLS MUST MATCH THE REAL TURN (2026-09-08): the server renders
        # tool schemas into the prompt prefix, so a prewarm without them
        # warms a prefix no chat ever sends. See llm_router.build_bonsai_tools.
        if tools:
            body["tools"] = tools
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            resp = await client.post(f"{BONSAI_HOST}/v1/chat/completions", json=body)
            resp.raise_for_status()
        return True
    except Exception as exc:
        print(f"[prewarm] failed (harmless): {exc}")
        return False


async def is_available() -> bool:
    """Is a llama-server answering on the Bonsai port right now? Cheap
    reachability check, same role amuse_integration.is_available() plays
    for image generation."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{BONSAI_HOST}/health")
            return resp.status_code == 200
    except httpx.HTTPError:
        return False


def files_present() -> bool:
    """Whether the model weights and server binary actually exist on disk
    -- lets the settings endpoint show Bonsai as an option only when it
    could genuinely start."""
    return os.path.isfile(BONSAI_MODEL_PATH) and os.path.isfile(BONSAI_SERVER_EXE)


async def ensure_running() -> bool:
    """Start llama-server if it isn't already answering, and wait until it
    can actually serve (health up) or the startup window runs out. Returns
    False rather than raising -- the caller (llm_router.generate) treats
    False as 'fall back to Ollama', never a crash.

    🔴 SERIALIZED SINCE 2026-09-17 (Barry: "fix the 27B empty responses").
    There was no lock here, and MEASURED on this machine three concurrent
    callers returned [False, True, False]: two callers got a failure from a
    perfectly healthy server that was simply still coming up. In the live path
    each False becomes a RuntimeError in llm_router, which calls
    record_failure(), and TWO failures trip the breaker -- so a moment of
    ordinary concurrency (the social loop, Sophie's watch and a chat landing
    together) put the WHOLE OFFICE on the 9b for ten minutes, with the server
    log showing nothing wrong because nothing was wrong. That is the "27B
    returns empty responses across nine seats" Sophie kept reporting: not the
    model, the orchestration around it. 322 starts in the log, 73 of them
    within five minutes of the previous one, is the same story in aggregate.

    The lock covers START and STOP together, because the fault was them
    interleaving. Everything inside must call the _locked helpers -- taking
    this lock twice in one task deadlocks.
    """
    global _server_proc, _bonsai_was_used
    if is_tripped():
        return False
    if await is_available():
        _bonsai_was_used = True
        return True
    if not files_present():
        return False
    _bonsai_was_used = True

    async with _gpu_lock:
        # Someone else may have started it while we waited for the lock --
        # that is the whole point, and it is a SUCCESS for this caller.
        if await is_available():
            return True
        return await _start_server_locked()


async def _start_server_locked() -> bool:
    """The real start. Only ever called holding _gpu_lock."""
    global _server_proc

    args = [
        BONSAI_SERVER_EXE,
        "-m", BONSAI_MODEL_PATH,
        "--host", "127.0.0.1",
        "--port", BONSAI_HOST.rsplit(":", 1)[-1],
        # --jinja: native OpenAI-style tool_calls support via the model's
        # own chat template -- required for the tool loop below.
        "--jinja",
        # SAMPLING = QWEN'S OWN SETTINGS (2026-10-07, Barry: "make sure the one im on is stable"). It ran on the
        # server defaults: temperature 1.0, presence penalty 0, repeat 1.0 -- the worst case for a 2-bit model,
        # and 45-61 LOOP STOP cuts a day (10-05..10-07). Qwen's card for this family, thinking mode: temp 0.6,
        # top-k 20, top-p 0.95, min-p 0; presence penalty 0-2 "to reduce endless repetitions" (higher can mix
        # languages, so 1.0). Judge by bonsai_events.log loop counts over real turns.
        "--temp", os.getenv("BONSAI_TEMP", "0.6"),
        "--top-k", os.getenv("BONSAI_TOP_K", "20"),
        "--top-p", os.getenv("BONSAI_TOP_P", "0.95"),
        "--min-p", os.getenv("BONSAI_MIN_P", "0"),
        "--presence-penalty", os.getenv("BONSAI_PRESENCE_PENALTY", "1.0"),
        "-ngl", "99",
        "-c", str(BONSAI_NUM_CTX),
        # ONE slot (2026-08-16). The default 4 slots each carry full-context
        # buffers, and at 65536 ctx that made the 16GB fit MARGINAL: with any
        # VRAM residue at start (comfy's torch cache, an Ollama runner not
        # yet evicted), fit-params quietly moved layers to CPU and generation
        # collapsed from ~45 tok/s to ~5.2 -- and the half-loaded server then
        # PERSISTED until something killed it. One user = one slot; the freed
        # memory is what makes the 64K window a reliable fit instead of a
        # coin flip. If slow generation ever recurs, check the server log for
        # tg t/s first -- ~5 means it spilled again.
        # TWO SLOTS + UNIFIED KV + RAM PROMPT CACHE since 2026-08-21 (Barry
        # approved: agent-switching was wiping the single slot's prompt
        # cache, so every switch paid a full ~50s re-read). Three flags
        # work together in this build:
        #  * --kv-unified: both slots SHARE one BONSAI_NUM_CTX-token KV
        #    pool (49152 since the same change) -- total KV memory is HALF
        #    the old 1x98304 fit, so no per-slot buffer doubling. First
        #    attempt used plain -np 2 without it and generation collapsed
        #    to 19.7 tok/s from the doubled buffers.
        #  * -np 2: two agents' prompts can be resident at once.
        #  * --cache-idle-slots + --cache-ram (default 8GB): an evicted
        #    prompt's KV state is saved to system RAM and RESTORED when
        #    that prompt returns -- agent switches restore from RAM
        #    instead of recomputing (llama.cpp PR 16391).
        # VRAM guard unchanged: tg t/s ~5 in the log = spill; fall back to
        # -np 1 without --kv-unified + ctx 98304 (env var) first.
        # Measured 2026-08-21: -np 2 + unified KV gave ~1s switch restores
        # but generation dropped to 14-29 tok/s (two live sequences tax the
        # Vulkan attention path). ONE slot + unified KV + cache-idle-slots
        # keeps the RAM save/restore across agent switches AND single-
        # sequence generation speed.
        "-np", "1",
        # --kv-unified: enables cache-idle-slots (RAM save/restore of
        # evicted prompts -- measured: agent switch-back re-read 618 tokens
        # instead of 28K). A/B on 2026-08-21 confirmed it does NOT cause the
        # gen-speed regression (14.6 tok/s with AND without it; suspected
        # GPU driver state after the LTX crawl -- reboot to clear).
        "--kv-unified",
        # ⚠️ THE ORIGINAL JUSTIFICATION FOR THIS FLAG WAS WRONG -- corrected
        # 2026-08-11 by reading data/bonsai_server.log rather than theorising.
        # It used to say office-sized prompts sent Bonsai into a thinking pass
        # that ate the whole max_tokens budget. The log says otherwise: the
        # failing calls show `eval time = 0.00 ms / 1 tokens` -- an immediate
        # EOS after ONE token, never a long think. And the flag did not fix
        # it: 3888-token prompts still emitted 1 token WITH budget=1024
        # applied, while a 6642-token prompt generated 700 fine, so prompt
        # size was never the variable either. The real failure was
        # content-dependent and stopped on its own once the 2026-08-07 brain
        # reorganisation changed the prompts; 6/6 real office prompts answered
        # on 2026-08-11.
        # The flag STAYS, but as a plain latency bound, not a bugfix: it caps
        # thinking at ~1024 tokens (~20s at measured speed) so a reasoning
        # pass can't run away. Do not remove it expecting to fix anything, and
        # do not re-add it as a cure if empty replies ever return -- go read
        # the server log for the token counts first.
        # RAISED 1024 -> 3072 on 2026-08-29. Barry, twice: "every
        # conversation needs, logic, reasoning and a quick ponder... it cant
        # be basic" and "they all need to think things through, including
        # Sophie and Priya and especially elliot... they have to truly
        # understand what i mean by things, even through my misspellings and
        # typo's."
        # This is a CEILING, NOT A FLOOR: a short message still finishes
        # thinking in a few hundred tokens and comes back as fast as before.
        # Only a genuinely hard question spends the extra room, which is
        # exactly where he wants the time going. Worst case adds ~40s of
        # thinking to the hardest asks (~20s -> ~60s at measured speed).
        # DIAL BACK HERE if replies to simple things start dragging -- this
        # one number is the whole knob. Module constant since 2026-09-15 so
        # the budget A/B (scripts/bench_reasoning_budget_*) can restart the
        # server at different values; env BONSAI_REASONING_BUDGET overrides.
        "--reasoning-budget", str(REASONING_BUDGET),
    ]
    # Vision tower (image input) rides along only if the file is actually
    # there -- its absence should degrade to text-only, not block startup.
    if os.path.isfile(BONSAI_MMPROJ_PATH):
        args += ["--mmproj", BONSAI_MMPROJ_PATH]
        # 2026-09-24: projector on the CPU frees ~0.9 GB so Bonsai 2 fits 98304 with room
        # (config.BONSAI_MMPROJ_GPU, measured in data/bench_bonsai2_kv_2026-09-24.json).
        if not BONSAI_MMPROJ_GPU:
            args += ["--no-mmproj-offload"]
    # Compressed KV cache (2026-09-22): q8_0 halves it, which is what lets
    # Bonsai 1 hold 98304 on 16GB without spilling. Quantized V needs flash
    # attention. See config.BONSAI_KV_TYPE for the measurement and the revert.
    if BONSAI_KV_TYPE and BONSAI_KV_TYPE != "f16":
        args += ["-fa", "on", "-ctk", BONSAI_KV_TYPE, "-ctv", BONSAI_KV_TYPE]
    if BONSAI_SPEC_TYPE and BONSAI_SPEC_TYPE != "none":
        args += ["--spec-type", BONSAI_SPEC_TYPE]
    # 2026-10-15 (Swift 1.5 trial): extra llama-server flags from .env, e.g. the MTP draft settings
    # "--spec-draft-n-max 2 --spec-draft-type-k q4_0 --spec-draft-type-v q4_0". Empty = nothing added.
    if os.getenv("BONSAI_EXTRA_ARGS", "").strip():
        import shlex
        args += shlex.split(os.getenv("BONSAI_EXTRA_ARGS"))

    try:
        os.makedirs(os.path.dirname(_SERVER_LOG_PATH), exist_ok=True)
        log_handle = open(_SERVER_LOG_PATH, "a", encoding="utf-8", errors="replace")
        log_handle.write(f"\n--- llama-server start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        log_handle.flush()
        _start_offset = log_handle.tell()
        _server_proc = subprocess.Popen(
            args,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            # Its own process group so it survives nothing it shouldn't and
            # doesn't get console signals meant for the backend.
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
        )
    except OSError:
        _server_proc = None
        return False

    deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
    proc = _server_proc
    while time.monotonic() < deadline:
        # A dead process is never coming up -- stop waiting immediately
        # instead of burning the whole startup window.
        # 2026-09-14: poll the LOCAL handle. stop_server() from another
        # coroutine (an eviction for a render or an Ollama seat) nulls the
        # module global mid-startup, and _server_proc.poll() then died with
        # "'NoneType' object has no attribute 'poll'" -- Sophie's watch
        # diagnosed that line thirteen times. If the global was cleared
        # under us, someone stopped this server on purpose: report failure.
        if _server_proc is not proc:
            return False
        if proc.poll() is not None:
            _server_proc = None
            return False
        if await is_available():
            # NEVER ON THE CPU (2026-10-10): the card came up disabled after a reboot, this server loaded anyway
            # ("ggml_cuda_init: failed to initialize ROCm: no ROCm-capable device is detected") and ran the 27B on
            # the CPU at ~3 tok/s for an hour -- every seat timed out, nothing said why. Refuse and say so; the
            # turn falls back, Sophie's watch (stack_watch.check_gpu_device) tells Barry the card's state.
            try:
                with open(_SERVER_LOG_PATH, "r", encoding="utf-8", errors="replace") as _fh:
                    _fh.seek(_start_offset)
                    _boot = _fh.read(200_000)
            except OSError:
                _boot = ""
            if "no ROCm-capable device" in _boot or "failed to initialize ROCm" in _boot:
                event("GPU NOT FOUND: llama-server started without the card (no ROCm-capable device) -- stopped, "
                      "NOT run on the CPU. Check Device Manager: the RX 9070 XT must be enabled.")
                await _stop_server_locked()
                return False
            return True
        await asyncio.sleep(1.0)
    # Ran out the clock without health -- kill the half-started process so
    # it doesn't sit there holding VRAM while we fall back to Ollama.
    # _locked: we already hold _gpu_lock, and taking it again deadlocks.
    await _stop_server_locked()
    return False


async def stop_server():
    """Free Bonsai's VRAM before something else (an Ollama model, ComfyUI)
    needs the GPU. Best-effort by design -- a failure here must never block
    the generation that's about to run.

    Takes _gpu_lock so a stop cannot land in the middle of a start (2026-09-17)
    -- that interleaving is what made healthy startups report failure and trip
    the breaker. Callers already holding the lock use _stop_server_locked.
    """
    # WHO STOPPED IT (2026-09-28): llama-server restarted 4x in 45 min with clean shutdowns and
    # nothing logged; each restart costs the next turn a full ~43 s prefill. Name the caller.
    if _server_proc is not None and _server_proc.poll() is None:
        try:
            import traceback
            _who = " <- ".join(f"{os.path.basename(f.filename)}:{f.lineno} {f.name}"
                               # 7 frames, not 3 (2026-09-30): 3 stopped inside llm_router and
                               # never named the module that asked for Ollama.
                               for f in traceback.extract_stack()[-8:-1][::-1])
            event(f"STOP requested: {_who}")
        except Exception:
            pass
    async with _gpu_lock:
        await _stop_server_locked()


async def _stop_server_locked():
    """The real stop. Only ever called holding _gpu_lock."""
    global _server_proc
    proc, _server_proc = _server_proc, None
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
            # Give it a moment to actually die (and release VRAM) --
            # terminate() alone returns before the GPU memory is free.
            for _ in range(20):
                if proc.poll() is not None:
                    break
                await asyncio.sleep(0.25)
            if proc.poll() is None:
                proc.kill()
        except OSError:
            pass
        return
    # Not started by us (e.g. launched manually via start_bonsai.ps1, or a
    # previous backend run) but still answering -- there's no PID to
    # terminate, so find it by port via netstat. Windows-specific, matching
    # this project's actual platform.
    if await is_available():
        port = BONSAI_HOST.rsplit(":", 1)[-1]
        try:
            out = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            ).stdout
            pids = {
                line.split()[-1]
                for line in out.splitlines()
                if f":{port}" in line and "LISTENING" in line
            }
            for pid in pids:
                subprocess.run(
                    ["taskkill", "/PID", pid, "/F"],
                    capture_output=True, timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
        except (OSError, subprocess.SubprocessError):
            pass
        return
    if not _bonsai_was_used:
        return
    # Zombie sweep -- real incident (2026-07-29): a llama-server orphaned by
    # an earlier backend kill released the port but hung on exit, invisible
    # to the port-based kill above while still holding GPU memory.
    # CRITICAL: match by COMMAND LINE, never by image name -- the AMD AI
    # Bundle Ollama runs its models through its own child process that is
    # ALSO named llama-server.exe (lib\ollama\llama-server.exe). An
    # image-name taskkill here killed Ollama's active runner on every chat
    # message (confirmed live: "warm" replies stayed as slow as cold ones
    # because the model was being murdered and reloaded each turn). Only
    # processes running OUR PrismML binary (tools\llama-prism) are fair game.
    try:
        ps = (
            "Get-CimInstance Win32_Process -Filter \"Name='llama-server.exe'\" | "
            "Where-Object { $_.CommandLine -like '*llama-prism*' } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def _shed_oldest_history(chat_messages: list, n_given: int, request_body: dict,
                         err: dict, office_name: str) -> bool:
    """CONTEXT FIT (2026-10-10). main._history_for_model caps the thread at a fixed 120K chars, but the room
    left differs per seat: Elliot's system prompt + tools run ~160K chars, and two of his turns after that fix
    still came to 99,728 / 99,233 tokens against n_ctx 98,304 -> 400 -> the 9b. llama-server's 400 states the
    exact prompt size, so drop just enough of the OLDEST history (never the system prompt, the current message,
    or this turn's tool rounds) to fit with room for the reply, in place, and let the caller retry once.
    Returns False when nothing can be dropped (the caller's fallback runs as before)."""
    n_prompt, n_ctx = int(err.get("n_prompt_tokens") or 0), int(err.get("n_ctx") or 0)
    last_given = n_given            # index of the current user message: system at 0, history 1..n_given-1
    if not n_prompt or not n_ctx or last_given <= 1:
        return False
    reserve = min(int(request_body.get("max_tokens") or 4096), 8192)
    total_chars = sum(len(json.dumps(m.get("content") or "")) for m in chat_messages)
    total_chars += len(json.dumps(request_body.get("tools") or []))
    chars_needed = (n_prompt - (n_ctx - reserve)) * total_chars / n_prompt
    shed, dropped = 0, 0
    while last_given > 1 and (shed < chars_needed or chat_messages[1].get("role") != "user"):
        shed += len(json.dumps(chat_messages[1].get("content") or ""))
        del chat_messages[1]
        last_given -= 1
        dropped += 1
    if shed < chars_needed:
        return False
    event(f"CONTEXT FIT {office_name}: {n_prompt} tokens > {n_ctx} -- dropped the {dropped} oldest history "
          f"messages ({shed:,} chars), retrying")
    return True


async def _post_fitting(client, request_body: dict, chat_messages: list, n_given: int, office_name: str):
    """The non-streaming request, with one CONTEXT FIT retry (see _shed_oldest_history). request_body["messages"]
    is chat_messages itself, so the shed applies to the retry and to every later round of this turn."""
    resp = await client.post(f"{BONSAI_HOST}/v1/chat/completions", json=request_body)
    if resp.status_code == 400 and "exceed_context_size_error" in resp.text:
        if _shed_oldest_history(chat_messages, n_given, request_body, resp.json().get("error") or {}, office_name):
            resp = await client.post(f"{BONSAI_HOST}/v1/chat/completions", json=request_body)
    return resp


async def call_bonsai(
    system_prompt: str,
    messages: list[dict],
    dispatch_tool_call,
    tools_list: list[dict] | None = None,
    tool_call_log: list | None = None,
    office_name: str | None = None,
    use_thinking: bool = True,
) -> str:
    """One agent turn against llama-server's OpenAI-compatible
    /v1/chat/completions, including the same multi-round tool loop the
    Ollama path runs. dispatch_tool_call is llm_router._dispatch_tool_call
    passed in by the caller -- identical real tool execution, no duplicate
    implementations. Raises on transport-level failure so the caller can
    run its fallback; returns a clean string otherwise."""
    chat_messages = [{"role": "system", "content": system_prompt}] + list(messages)
    tools = tools_list or []
    valid_names = {t["function"]["name"] for t in tools}

    async with httpx.AsyncClient(timeout=_scaled(_REQUEST_TIMEOUT_SECONDS)) as client:
        message = {}
        # TOOL-RESULT BUDGET (2026-09-08). Sophie's first store-ops turn ran 8
        # tool rounds (3x browse_site, system_health, read_project_file...) and
        # the prompt hit 52,771 tokens against a 49,152 window: llama-server
        # 400'd and the coder fallback wrote the answer. Results are capped
        # per call and per turn, and a clipped result SAYS it was clipped and
        # how to get the rest, so the model narrows instead of guessing.
        tool_chars_left = TOOL_RESULT_BUDGET_CHARS
        _turn_t0 = time.monotonic()
        for _round in range(tool_rounds() if tools else 1):
            # TIME CEILING (2026-09-28, Barry: "I need them to be totally
            # reliable"). Rounds were capped but time was not: Priya's barcode
            # brief searched for 23 minutes, each round slower than the last,
            # until one read passed the 300s limit and tripped the breaker for
            # the whole office. Past the ceiling the turn stops searching and
            # takes the same forced-answer pass as running out of rounds.
            if (tools and _round > 0
                    and time.monotonic() - _turn_t0 > _scaled(TURN_TIME_CEILING_SECONDS)):
                event(f"TIME CEILING {office_name}: {int(time.monotonic() - _turn_t0)}s after "
                      f"{_round} tool rounds -- answering from what it has")
                break
            request_body = {
                "model": BONSAI_MODEL_NAME,  # informational -- server serves one model
                "messages": chat_messages,
                "stream": False,
                **seat_sampling(office_name),      # 2026-10-17: each seat its own temperature/penalties

                # THE SLOWNESS FIX (2026-08-16). Without this the server
                # re-read the ENTIRE prompt on every message: measured
                # 44,743 ms to reprocess 38,340 tokens, while generating the
                # actual reply took 2-4 s. Barry's "he responds slow" was
                # ~90% prompt re-reading. This fork does not default it on,
                # so it has to be asked for explicitly; the agent prompt is
                # a stable prefix (the per-message parts ride at the end),
                # which is exactly the shape prefix caching wants.
                "cache_prompt": True,
                # Mirrors the Ollama path's num_predict backstop: a
                # degenerate run can't consume unbounded tokens/time.
                # Quick replies (short casual messages) get a lower cap --
                # see max_tokens_override at the top of this file.
                "max_tokens": max_tokens(),
                # Per-message thinking budget (2026-09-15) -- see _think_fields.
                **_think_fields(),
            }
            # THINKING OFF, FOR REAL (2026-09-17). Until today use_thinking
            # never reached this function -- the flag only ever governed the
            # Ollama fallback, so "thinking off" on a Bonsai seat was a no-op
            # (the 08-29 social finding was measured on 9b fallback turns).
            # Barry: thinking off at home and in group chats. The probe on
            # 2026-09-08 showed `chat_template_kwargs.enable_thinking=false`
            # is the only hard stop on this fork; the budget keys are dropped
            # with it so the cut-detector (which keys off a budget with no
            # template kwargs) stays quiet. Work turns never come through here
            # with use_thinking=False.
            _schema = json_schema_override.get()
            if _schema:
                use_thinking = False                 # the grammar would fight the <think> block
                tools = None                         # a locked pass answers, it does not call
                request_body["response_format"] = {"type": "json_object", "schema": _schema}
            if not use_thinking:
                request_body.pop("thinking_budget_tokens", None)
                request_body.pop("thinking_budget_message", None)
                request_body["chat_template_kwargs"] = {"enable_thinking": False}
            if tools:
                request_body["tools"] = tools
            # STREAMED so Barry can watch the reasoning arrive (see
            # _stream_round). Identical result either way; if streaming fails
            # for any reason at all we fall back to the proven request rather
            # than risk the answer.
            try:
                message = await _stream_round(client, request_body, office_name or "")
                if message.get("loop_cut"):
                    message = await _finish_after_loop(client, request_body, message,
                                                       office_name or "")
            except Exception as _stream_exc:
                print(f"[bonsai] stream failed ({type(_stream_exc).__name__}), "
                      f"using non-streaming: {_stream_exc}")
                resp = await _post_fitting(client, request_body, chat_messages, len(messages), office_name or "")
                resp.raise_for_status()
                data = resp.json()
                choices = data.get("choices") or []
                message = (choices[0].get("message") or {}) if choices else {}
                if choices and choices[0].get("finish_reason"):
                    message["finish_reason"] = choices[0]["finish_reason"]
            tool_calls = message.get("tool_calls") or []
            if not tool_calls and tools:
                # Text-shaped tool calls (see _parse_pseudo_xml_calls):
                # execute them like real ones instead of leaking the syntax
                # or dropping the intent -- parity with the Ollama path's
                # _try_parse_pseudo_tool_calls fallback.
                tool_calls = _parse_pseudo_xml_calls(
                    message.get("content", ""), valid_names)
                if not tool_calls:
                    # Bare `read_skill("x")` on its own line (2026-08-31).
                    tool_calls = _parse_pseudo_plain_calls(
                        message.get("content", ""), tools)
                if not tool_calls:
                    tool_calls = _parse_pseudo_json_calls(message.get("content", ""), valid_names)

            if not tool_calls:
                cleaned = _clean_content(message.get("content", ""), tools)
                _capped = (quick_reply.get()
                           and request_body.get("max_tokens", DEFAULT_MAX_TOKENS) < DEFAULT_MAX_TOKENS
                           and not request_body.get("chat_template_kwargs")
                           and (not cleaned or message.get("finish_reason") == "length"))
                if _capped:
                    # The quick cap was HIT: either reasoning ate everything
                    # (empty reply) or -- measured on the first live test --
                    # the cap landed INSIDE the answer ("Yeah, a two"). A
                    # truncated reply is worse than a slow one, so ONE retry
                    # with thinking off and the full budget; the message was
                    # short casual talk by construction, so a direct reply is
                    # the honest answer. Logged so the rate can be measured.
                    print(f"[quick-reply] {office_name}: cap {request_body['max_tokens']} hit "
                          f"(finish={message.get('finish_reason')}, content={len(cleaned)} chars) "
                          f"-- retrying once without thinking")
                    # ⚠️ THE RETRY MUST NOT DESTROY A USABLE ANSWER (2026-09-19,
                    # Barry: "something messed up"). This overwrote `cleaned`
                    # unconditionally. Measured on ilnora's "generate that":
                    # attempt 1 hit the cap with 1,728 REAL chars; the retry
                    # generated 16 tokens that cleaned to NOTHING, and Barry
                    # got an empty reply where a truncated-but-usable one had
                    # existed a second earlier. A retry is an attempt to do
                    # BETTER -- so it only stands if it actually produced
                    # something. Otherwise keep what we had.
                    _first_msg, _first_clean = message, cleaned
                    retry = dict(request_body)
                    retry["max_tokens"] = DEFAULT_MAX_TOKENS
                    retry["chat_template_kwargs"] = {"enable_thinking": False}
                    try:
                        message = await _stream_round(client, retry, office_name or "")
                    except Exception:
                        resp = await client.post(f"{BONSAI_HOST}/v1/chat/completions", json=retry)
                        resp.raise_for_status()
                        _ch = resp.json().get("choices") or []
                        message = (_ch[0].get("message") or {}) if _ch else {}
                    cleaned = _clean_content(message.get("content", ""), tools)
                    if not cleaned.strip() and _first_clean.strip():
                        print(f"[quick-reply] {office_name}: retry came back empty "
                              f"-- keeping the first answer ({len(_first_clean)} chars, truncated)")
                        message, cleaned = _first_msg, _first_clean
                # THE SPILL GUARD (2026-09-15): a budget cut that landed
                # mid-thought leaks reasoning into the answer. ONE retry with
                # the budget lifted; the retry's answer stands either way.
                _cut = _budget_cut_fired(message, request_body.get("thinking_budget_tokens"))
                _spill_why = ("head" if _looks_spilled(cleaned)
                              else "narrated-then-addressed" if (_cut and _looks_spilled_after_cut(cleaned))
                              else "")
                _budgeted = bool(request_body.get("thinking_budget_tokens")) and not request_body.get("chat_template_kwargs")
                _stripped = None
                if _budgeted and _spill_why == "narrated-then-addressed":
                    _stripped = _strip_narration(cleaned)
                if _budgeted and _stripped:
                    # STRIP FIRST (2026-09-15): the leaked narration is cut
                    # off and the addressed reply returned as-is, <1 ms, no
                    # second generation. Retry only when stripping is unsafe.
                    _kept, _dropped = _stripped
                    print(f"[think-budget] {office_name}: leaked narration stripped "
                          f"({len(_dropped)} chars) after a budget cut")
                    _log_cut(office_name, message, cleaned, "strip", _dropped, _spill_why)
                    cleaned = _kept
                elif _budgeted and _cut and not _spill_why:
                    _log_cut(office_name, message, cleaned, "clean", None)
                # ...BUT NEVER RETRY A TURN THAT ALREADY HIT THE CEILING
                # (2026-09-19). Measured on ilnora: pass 1 ended at exactly
                # max_tokens with a long answer, the unlimited retry re-ran
                # the same prompt with the thinking cap REMOVED, spent all
                # 4096 tokens reasoning and produced nothing. ~2.5 minutes of
                # guaranteed waste -- a turn that overran the ceiling WITH a
                # thinking cap cannot do better without one. Keep the answer
                # we already have; the strip path above still runs (free).
                _hit_ceiling = message.get("finish_reason") == "length"
                if _budgeted and _spill_why and not _stripped and _hit_ceiling:
                    print(f"[think-budget] {office_name}: reasoning spilled but the reply hit the "
                          f"{request_body.get('max_tokens')}-token ceiling -- keeping this answer, "
                          f"an unlimited retry would only overrun again")
                    _log_cut(office_name, message, cleaned, "clean", None, _spill_why)
                if _budgeted and _spill_why and not _stripped and not _hit_ceiling:
                    print(f"[think-budget] {office_name}: reasoning spilled into the answer at "
                          f"{request_body['thinking_budget_tokens']} tokens ({_spill_why}, "
                          f"cut_fired={_cut}) -- retrying once unlimited")
                    _log_cut(office_name, message, cleaned, "retry", None, _spill_why)
                    _spill_msg, _spill_clean = message, cleaned
                    retry = {k: v for k, v in request_body.items()
                             if k not in ("thinking_budget_tokens", "thinking_budget_message")}
                    try:
                        message = await _stream_round(client, retry, office_name or "")
                    except Exception:
                        resp = await client.post(f"{BONSAI_HOST}/v1/chat/completions", json=retry)
                        resp.raise_for_status()
                        _ch = resp.json().get("choices") or []
                        message = (_ch[0].get("message") or {}) if _ch else {}
                    cleaned = _clean_content(message.get("content", ""), tools)
                    # A RETRY ONLY STANDS IF IT PRODUCED SOMETHING (the
                    # 2026-09-19 rule). Unlimited thinking is the WRONG
                    # direction when thinking is what ate the budget: this
                    # retry can burn the whole reply ceiling and come back
                    # empty, replacing a messy-but-real answer with silence.
                    if not cleaned.strip() and _spill_clean.strip():
                        print(f"[think-budget] {office_name}: unlimited retry came back empty "
                              f"-- keeping the first answer ({len(_spill_clean)} chars)")
                        message, cleaned = _spill_msg, _spill_clean
                if not cleaned.strip():
                    # 🔴 NO REPLY AT ALL (2026-09-19, Barry: "i got a no reply
                    # from ilnora again. i think she thinks too long"). His
                    # read was right and the server log names it: eval time =
                    # 4096 tokens -- EXACTLY max_tokens -- twice in a row, so
                    # reasoning spent the entire reply budget and the answer
                    # never started. 426 seconds, then nothing on screen.
                    # The `pass` below said the router would fall back; it
                    # does NOT -- call_bonsai_with_fallback treats a returned
                    # string as a success, so an empty string was delivered as
                    # an answer. Two things now happen instead:
                    #   1. ONE retry with thinking OFF, which the 2026-09-08
                    #      probe measured as the only hard stop on this fork.
                    #      Turning thinking off is the right direction here --
                    #      the failure IS that it thought to the ceiling.
                    #   2. Still empty ⇒ RAISE, so the promised Ollama
                    #      fallback actually answers. An agent going silent
                    #      is worse than an agent answering on the 9b.
                    if use_thinking and not request_body.get("chat_template_kwargs"):
                        print(f"[bonsai] {office_name}: empty reply "
                              f"(finish={message.get('finish_reason')}, max_tokens="
                              f"{request_body.get('max_tokens')}) -- retrying once with thinking off")
                        retry = {k: v for k, v in request_body.items()
                                 if k not in ("thinking_budget_tokens", "thinking_budget_message", "max_tokens")}
                        retry["max_tokens"] = DEFAULT_MAX_TOKENS
                        retry["chat_template_kwargs"] = {"enable_thinking": False}
                        try:
                            message = await _stream_round(client, retry, office_name or "")
                        except Exception:
                            resp = await client.post(f"{BONSAI_HOST}/v1/chat/completions", json=retry)
                            resp.raise_for_status()
                            _ch = resp.json().get("choices") or []
                            message = (_ch[0].get("message") or {}) if _ch else {}
                        cleaned = _clean_content(message.get("content", ""), tools)
                    if not cleaned.strip():
                        event(f"EMPTY REPLY {office_name}: nothing after a thinking-off retry "
                              f"(finish={message.get('finish_reason')})")
                        raise EmptyReply(
                            f"Bonsai returned an empty reply for {office_name} "
                            f"(finish={message.get('finish_reason')}, "
                            f"max_tokens={request_body.get('max_tokens')}) -- "
                            f"reasoning most likely consumed the whole reply budget"
                        )
                    # History (2026-07-29): Bonsai deterministically emitted an
                    # immediate EOS on this office's real system prompts --
                    # content-dependent, reproduced with reasoning on AND off,
                    # with and without tools, while same-sized synthetic
                    # prompts answered fine. 8/8 in-office calls came back
                    # empty; the only two "successes" on record bypassed the
                    # agent path (traces show office_name=None).
                    # RESOLVED 2026-08-11: it no longer reproduces. 6/6 real
                    # office prompts answered substantively, and a 3-way
                    # benchmark put Bonsai at 5/5 logic and 3x the 9b's
                    # reasoning speed. Nothing here was fixed deliberately --
                    # the 2026-08-07 brain reorganisation changed the prompt
                    # content, which is what the failure keyed on.
                    # That history is why the guard above raises rather than
                    # returning "": an agent must never go silent because of a
                    # backend quirk, and the quirk is dormant, not disproven.
                return cleaned

            # Run each requested tool, feed results back, take another pass.
            message.pop("finish_reason", None)
            chat_messages.append(message)
            _seen_pixels: list[str] = []
            for call in tool_calls:
                fn = call.get("function", {})
                name = fn.get("name", "")
                raw_args = fn.get("arguments", {})
                # OpenAI shape sends arguments as a JSON *string*; Ollama
                # sends a dict. Accept both so the shared dispatcher always
                # sees a dict.
                if isinstance(raw_args, str):
                    try:
                        raw_args = json.loads(raw_args)
                    except (json.JSONDecodeError, ValueError):
                        raw_args = {}
                if name not in valid_names:
                    result = {"error": f"Unknown tool: {name}"}
                else:
                    result = await dispatch_tool_call(name, raw_args, office_name=office_name)
                if tool_call_log is not None:
                    tool_call_log.append(name)
                    # claim_net "restart": only a restart that was really scheduled backs "I restarted" (2026-10-10)
                    if (name == "restart_backend" and isinstance(result, dict)
                            and result.get("status") == "scheduled"):
                        tool_call_log.append("restart_backend:scheduled")
                if isinstance(result, dict) and result.get("_pixels"):
                    _seen_pixels.extend(p for p in result.pop("_pixels") if p)
                content = json.dumps(result)
                claim_net.record_tool_result(content)   # numbers check: what the model saw (2026-09-24)
                cap = min(TOOL_RESULT_MAX_CHARS, max(tool_chars_left, 1_500))
                if len(content) > cap:
                    content = (content[:cap]
                               + f' ...[CLIPPED: {len(content) - cap} more chars not shown -- the '
                                 f'context window is nearly full. Ask for a narrower read '
                                 f'(a smaller file range, one product, one section).]')
                tool_chars_left = max(0, tool_chars_left - len(content))
                chat_messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": content,
                })
            # THEY SEE THE PIXELS (2026-09-23, Barry: "he needs to be able to
            # read pixels and all. i need them all to truly see"). The look
            # tools used to hand the agent a CAPTION written by the 9b vision
            # model -- a description of the picture, never the picture. This
            # server runs with Bonsai's own vision projector (--mmproj), so the
            # opened files now go to the agent's own model as real images, next
            # to the caption, which stays as a hint.
            if _seen_pixels:
                parts = _pixel_parts(_seen_pixels)
                if parts:
                    chat_messages.append({"role": "user", "content": [
                        {"type": "text", "text": (
                            "These are the actual pictures you just opened, at full "
                            "detail. Look at them yourself. The written description "
                            "above is only a hint -- where it disagrees with what you "
                            "see here, trust the pixels.")}] + parts})
                    print(f"[vision] {office_name}: {len(parts)} picture(s) sent as pixels", flush=True)

        # Out of tool rounds. The old behaviour gave up here with a guard
        # string -- measured 2026-08-16 on Sophie's seat, an open
        # investigate-shaped question burned every round on file reads and
        # Barry got 58 chars of nothing after ~100s. The tool RESULTS are
        # all sitting in chat_messages, so the fix is one final pass with
        # the tools taken away: the model must synthesize an answer from
        # what it already gathered. The guard string remains only as the
        # last resort if even that comes back empty.
        if message.get("tool_calls"):
            chat_messages.append(message)
            chat_messages.append({"role": "user", "content": OUT_OF_ROUNDS_NUDGE})
            request_body = {
                "model": BONSAI_MODEL_NAME,
                "messages": chat_messages,
                "stream": False,
                **seat_sampling(office_name),
                # THE SLOWNESS FIX (2026-08-16). Without this the server
                # re-read the ENTIRE prompt on every message: measured
                # 44,743 ms to reprocess 38,340 tokens, while generating the
                # actual reply took 2-4 s. Barry's "he responds slow" was
                # ~90% prompt re-reading. This fork does not default it on,
                # so it has to be asked for explicitly; the agent prompt is
                # a stable prefix (the per-message parts ride at the end),
                # which is exactly the shape prefix caching wants.
                "cache_prompt": True,
                # 2026-10-10: a turn given a BIGGER reply cap keeps it here too. Ilnora's video turns (16,384) hit
                # the ceiling and then had to fit a 2,000-word script + thinking into 4,096 -- cut every time
                # ("FINAL CUT SHORT", 23:18 / 00:45 / 01:08). Normal seats are unchanged (max(4096, their cap)).
                "max_tokens": max(4096, max_tokens()),
                **_think_fields(),
                # deliberately NO tools -- answering is the only move left
            }
            if not use_thinking:
                request_body.pop("thinking_budget_tokens", None)
                request_body.pop("thinking_budget_message", None)
                request_body["chat_template_kwargs"] = {"enable_thinking": False}
            resp = await _post_fitting(client, request_body, chat_messages, len(messages), office_name or "")
            resp.raise_for_status()
            choices = resp.json().get("choices") or []
            final = ((choices[0].get("message") or {}).get("content", "")) if choices else ""
            final = _clean_content(final, tools)
            # CUT OFF BY THE CEILING (2026-09-28): Sophie's security answer
            # ended mid-list at "2." -- the synthesis ran with thinking on inside
            # a 4096 ceiling, and the reasoning ate it. A reply that hit the
            # length limit gets the same thinking-OFF pass as a stub; the longer
            # real answer wins.
            _cut_short = bool(choices) and choices[0].get("finish_reason") == "length"
            if _cut_short:
                event(f"FINAL CUT SHORT {office_name}: synthesis hit max_tokens -- retrying with thinking off")
            # 2026-09-06: the synthesis itself came back as "Let me read the
            # memory.py file..." -- a stub that still wants a tool it no
            # longer has. One harder push before giving up.
            if _looks_like_stub(final) or _cut_short:
                chat_messages.append({"role": "assistant", "content": final})
                chat_messages.append({"role": "user", "content": (
                    "[System: that reply was CUT OFF mid-sentence by the length limit. "
                    "Write the COMPLETE reply again from the start, from the tool results "
                    "already above -- tighter, so it fits: the findings and the answer, "
                    "every item finished. Where something is unread, say 'unverified'.]"
                    if _cut_short and not _looks_like_stub(final) else
                    "[System: that was not an answer -- it announced a step you cannot "
                    "take, because the tools are gone for this turn. Write the COMPLETE "
                    "reply now from the tool results already above: the plan, the "
                    "findings, the answer. Where something is unread, say 'unverified' "
                    "and move on. No 'let me', no 'I will now'.]")})
                # 2026-09-27: run this final synthesis with thinking OFF so the
                # model goes straight to the answer instead of dithering in the
                # reasoning budget over the two nudge messages. (The loop
                # detector stays as the backstop.)
                request_body["messages"] = chat_messages
                if use_thinking:
                    request_body["chat_template_kwargs"] = {"enable_thinking": False}
                resp = await _post_fitting(client, request_body, chat_messages, len(messages), office_name or "")
                resp.raise_for_status()
                choices = resp.json().get("choices") or []
                final2 = _clean_content(((choices[0].get("message") or {}).get("content", "")) if choices else "", tools)
                # A cut-off first answer is still real text: the retry replaces
                # it only if it is a real answer too (not a stub) -- and a retry
                # that was ALSO cut short must be at least as long to win.
                _retry_cut = bool(choices) and choices[0].get("finish_reason") == "length"
                if final2 and not _looks_like_stub(final2) and (
                        not _cut_short or not _retry_cut or len(final2) >= len(final)):
                    final = final2
            return final or "[Agent kept searching without settling on a final answer.]"
        return _clean_content(message.get("content", ""), tools) or "[Agent kept searching without settling on a final answer.]"
