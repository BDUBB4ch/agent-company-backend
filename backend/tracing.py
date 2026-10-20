"""
Local, code-controlled trace log for every Ollama call this backend makes,
so Sophie (Engineer) has real data to investigate silent agent failures --
a loop, an empty reply, dropped context -- instead of just her own
impression of a conversation.

Two outputs per turn, both best-effort and never allowed to break a real
chat request:
1. One JSON line appended to data/traces.jsonl -- the canonical record.
   Sophie's investigate_traces tool (see llm_router.py/main.py) reads THIS,
   not Workshop's database -- Workshop's internal SQLite schema isn't a
   documented public interface for third parties to query, so building
   failure-detection against our own structured log keeps that logic
   independent of whatever Workshop's schema happens to be this version.
2. A mirrored span POSTed to Raindrop Workshop (github.com/raindrop-ai/
   workshop, MIT-licensed, fully local -- no account, no API key, no cloud
   dependency) at http://localhost:5899/v1/traces, so Barry can also watch
   traces live in Workshop's own UI if he wants to. Confirmed working via a
   direct test POST before wiring this in: Workshop accepted the span
   ({"ok":true,"spansIngested":1}) and it landed in its own `spans` SQLite
   table. If Workshop isn't running, this mirror is silently a no-op --
   routine, not an error.
"""
import contextvars
import difflib
import json
import time
import uuid
import datetime
from pathlib import Path

import httpx

from config import DATA_DIR

TRACES_PATH = Path(DATA_DIR) / "traces.jsonl"
WORKSHOP_URL = "http://localhost:5899/v1/traces"

# Sentinel strings already returned by llm_router.py's call_ollama in its
# real failure paths -- reused here rather than plumbing new return values
# through the existing function, since these exact strings are already the
# ground truth for what happened.
_NO_CONTENT = "[Ollama returned no content]"
_ROUND_LIMIT = "[Agent kept searching without settling on a final answer.]"
_CONNECT_PREFIX = "[Could not reach Ollama"

MAX_CONTENT_CHARS = 800

# Real bug found and confirmed by direct replay, not assumed: Ollama's own
# baked-in Modelfile default for huihui_ai/qwen3-abliterated:8b-v2 sets
# repeat_penalty=1 (the neutral/no-op value), which let Taliyah answer two
# genuinely different, back-to-back user corrections with near-identical
# text -- confirmed reproducible by replaying the exact real conversation
# directly against Ollama, then confirming an explicit repeat_penalty
# override (see llm_router.py) breaks the repetition. That fix addresses
# the root cause going forward; this threshold exists so Sophie can also
# actually SEE it happening if it ever recurs (a different model, a
# different quirk), rather than the trace log staying silent about it the
# way it did the first time -- which is exactly the gap Barry caught.
_NEAR_DUPLICATE_SIMILARITY_THRESHOLD = 0.75
_NEAR_DUPLICATE_MIN_LENGTH = 40  # avoids flagging two short generic replies ("Got it.") as duplicates


def _is_near_duplicate(a: str, b: str) -> bool:
    if len(a) < _NEAR_DUPLICATE_MIN_LENGTH or len(b) < _NEAR_DUPLICATE_MIN_LENGTH:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= _NEAR_DUPLICATE_SIMILARITY_THRESHOLD


def _detect_failure_signature(final_content: str, tool_calls: list[str], previous_content: str | None) -> str | None:
    if final_content.startswith(_CONNECT_PREFIX):
        return "connect_error"
    if final_content == _NO_CONTENT:
        return "no_content"
    if final_content == _ROUND_LIMIT:
        return "tool_round_limit_exceeded"
    # Same tool called 3+ times in a row is a real loop signature even on a
    # turn that eventually did produce an answer -- EXCEPT for research tools,
    # where repetition is the job: Priya searched the web eight times with
    # eight different queries on one brief (2026-09-02) and was logged as a
    # "loop" four times, which fed the "calls are failing" banner. Only tool
    # NAMES are logged here, so a research tool needs a much longer run to
    # count; a non-research tool (a write, a delegate) still trips at 3.
    _RESEARCH = {"search_web", "read_project_file", "lookup_product", "read_product",
                 "browse_site", "browse_gotchoback", "read_scene", "search_script",
                 "read_skill", "investigate_traces", "check_omnisend", "list_project_directory",
                 "system_health", "search_project",
                 # 2026-10-11: Ilnora's research reads, and her draft workspace -- video_draft is MEANT to be
                 # called several times a turn (start, notes, add_parts x3); 4 of her Wolf's Blood turns were
                 # stamped "repeated_tool_loop" and lit "Calls are failing outright" for Barry with nothing failing.
                 "pubmed_search", "search_library", "read_library", "read_web_page", "read_barrys_file",
                 "list_files", "video_draft", "check_video", "office_ops", "channel_stats"}
    # 2026-10-15: remember_lesson is a write, not research -- but a review brief
    # can legitimately file several lessons in one pass (ilnora's 17:41 review:
    # four calls, coherent final reply, no model error). The flat 3-call trip
    # stamped that as a loop and lit the "build is broken" banner with nothing
    # failing. Give legitimate multi-call writes their own higher limit instead
    # of lumping them in with research, so a real remember_lesson write-loop
    # (same lesson re-filed forever) is still catchable at a higher run.
    _PER_TOOL_LIMITS = {"remember_lesson": 8}
    run = 1
    for i in range(1, len(tool_calls)):
        if tool_calls[i] == tool_calls[i - 1]:
            run += 1
            limit = _PER_TOOL_LIMITS.get(tool_calls[i], 12 if tool_calls[i] in _RESEARCH else 3)
            if run >= limit:
                return "repeated_tool_loop"
        else:
            run = 1
    if previous_content and _is_near_duplicate(final_content, previous_content):
        return "near_duplicate_reply"
    return None


def _last_reply_for_office(office_name: str | None) -> str | None:
    if not office_name:
        return None
    recent = query_recent_traces(office_name=office_name, limit=1)
    return recent[0]["final_content"] if recent else None


call_context: contextvars.ContextVar[str] = contextvars.ContextVar(
    "call_context", default="chat")
"""What KIND of call this is: "chat" (Barry asked something), "social" (break
room / DM / group chat), "reflection" (idle inner life), "system" (summaries).

WHY IT EXISTS (2026-08-31): degradation.py flags "replies coming back stubby"
when too many replies are under 200 chars. That rule was written when every
call was a work answer. Since the break room and the personal channel were
built, most calls are CONVERSATION -- and a 120-character line in a DM is a
person talking, not a defect. The monitor was reporting 76% stubby off its own
healthy chit-chat. A short answer is only evidence of a problem when someone
actually asked a real question.
"""


def set_call_context(kind: str):
    """Returns the token so a caller can restore the previous value."""
    return call_context.set(kind)


def reset_call_context(token) -> None:
    try:
        call_context.reset(token)
    except (ValueError, LookupError):
        pass


def record_turn(
    office_name: str | None,
    model: str,
    tool_calls: list[str],
    final_content: str,
    duration_ms: float,
    error: str | None = None,
    prompt_chars: int | None = None,
) -> dict:
    """Best-effort -- a tracing failure must never break a real chat turn.
    Returns the record that was written (or attempted)."""
    if error:
        failure = "exception"
    else:
        previous_content = _last_reply_for_office(office_name)
        failure = _detect_failure_signature(final_content or "", tool_calls, previous_content)
    record = {
        "id": uuid.uuid4().hex,
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "office_name": office_name,
        "model": model,
        "tool_calls": tool_calls,
        "final_content": (final_content or "")[:MAX_CONTENT_CHARS],
        "duration_ms": round(duration_ms, 1),
        "error": error,
        "failure_signature": failure,
        # see call_context above: lets degradation.py judge a WORK answer
        # differently from a line of break-room conversation.
        "context": call_context.get(),
        "prompt_chars": prompt_chars,
    }
    try:
        TRACES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(TRACES_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        pass
    _mirror_to_workshop(record, duration_ms)
    return record


def _mirror_to_workshop(record: dict, duration_ms: float) -> None:
    try:
        now_ns = time.time_ns()
        span = {
            "resourceSpans": [{
                "resource": {"attributes": [
                    {"key": "service.name", "value": {"stringValue": "agent-company-backend"}}
                ]},
                "scopeSpans": [{
                    "scope": {"name": "agent-company-backend"},
                    "spans": [{
                        "traceId": record["id"].ljust(32, "0")[:32],
                        "spanId": record["id"][:16],
                        "name": f"agent_turn:{record['office_name'] or 'unknown'}",
                        "kind": 1,
                        "startTimeUnixNano": str(now_ns - int(duration_ms * 1_000_000)),
                        "endTimeUnixNano": str(now_ns),
                        "attributes": [
                            {"key": "office_name", "value": {"stringValue": record["office_name"] or ""}},
                            {"key": "model", "value": {"stringValue": record["model"] or ""}},
                            {"key": "tool_calls", "value": {"stringValue": ",".join(record["tool_calls"])}},
                            {"key": "failure_signature", "value": {"stringValue": record["failure_signature"] or ""}},
                            {"key": "final_content", "value": {"stringValue": record["final_content"]}},
                        ],
                    }],
                }],
            }]
        }
        with httpx.Client(timeout=1.0) as client:
            client.post(WORKSHOP_URL, json=span)
    except Exception:
        pass


def query_recent_traces(office_name: str | None = None, only_failures: bool = False, limit: int = 50) -> list[dict]:
    """Read-only. Used by Sophie's investigate_traces tool. Most recent
    first."""
    if not TRACES_PATH.exists():
        return []
    records = []
    with open(TRACES_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    records.reverse()
    if office_name:
        records = [r for r in records if r.get("office_name") == office_name]
    if only_failures:
        records = [r for r in records if r.get("failure_signature")]
    return records[:limit]


def has_recent_verified_failure(office_name: str) -> bool:
    """Ground-truth gate for Sophie's auto-fix path (see main.py's
    submit_agent_fix dispatch). Sophie's own belief that something is 'an
    actual fix' is never enough on its own -- this checks the real trace
    data for that agent and confirms a genuine, code-detected failure
    signature actually shows up. If it doesn't, the fix always routes
    through the approval queue instead, regardless of what Sophie claims."""
    return len(query_recent_traces(office_name=office_name, only_failures=True, limit=10)) > 0
