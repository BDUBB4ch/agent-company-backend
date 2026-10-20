"""QUICK REPLIES (2026-09-08, Barry: "build the reasoning budget thing for
short messages"). One-shot patch, asserts every anchor, refuses to run twice.
Three layers: max_tokens cap + no-thinking retry in bonsai_llm.py, the
classifier + ContextVar set in main.py, the static depth rule in agents.py."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B = os.path.join(ROOT, "backend")


def patch(fn, pairs):
    p = os.path.join(B, fn)
    s = open(p, encoding="utf-8").read()
    for old, new in pairs:
        assert s.count(old) == 1, f"{fn}: anchor not found exactly once: {old[:60]!r}"
        s = s.replace(old, new)
    tmp = p + ".tmp"
    open(tmp, "w", encoding="utf-8").write(s)
    os.replace(tmp, p)
    print(f"  patched {fn}")


if "quick_reply.get()" in open(os.path.join(B, "bonsai_llm.py"), encoding="utf-8").read():
    sys.exit("already applied")

patch("bonsai_llm.py", [
    (
        '''                "cache_prompt": True,
                # Mirrors the Ollama path's num_predict backstop: a
                # degenerate run can't consume unbounded tokens/time.
                "max_tokens": 4096,
            }''',
        '''                "cache_prompt": True,
                # Mirrors the Ollama path's num_predict backstop: a
                # degenerate run can't consume unbounded tokens/time.
                # Quick replies (short casual messages) get a lower cap --
                # see max_tokens_override at the top of this file.
                "max_tokens": max_tokens(),
            }''',
    ),
    (
        '''            if not tool_calls:
                cleaned = _clean_content(message.get("content", ""), tools)
                if not cleaned:''',
        '''            if not tool_calls:
                cleaned = _clean_content(message.get("content", ""), tools)
                if (not cleaned and quick_reply.get()
                        and request_body.get("max_tokens", DEFAULT_MAX_TOKENS) < DEFAULT_MAX_TOKENS
                        and not request_body.get("chat_template_kwargs")):
                    # The quick cap swallowed the answer (reasoning ran to the
                    # cap, nothing left for the reply). ONE retry with thinking
                    # off and the full budget -- the message was short casual
                    # talk by construction, so a direct reply is the honest
                    # answer. Logged so the rate can be measured.
                    print(f"[quick-reply] {office_name}: cap {request_body['max_tokens']} "
                          f"swallowed the answer -- retrying once without thinking")
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
                if not cleaned:''',
    ),
])

patch("main.py", [
    (
        '''def _health_ask(message: str) -> bool:
    return bool(_HEALTH_ASK_RE.search(message or ""))''',
        '''def _health_ask(message: str) -> bool:
    return bool(_HEALTH_ASK_RE.search(message or ""))


# QUICK REPLY (2026-09-08, Barry: "build the reasoning budget thing for short
# messages"). A short casual message with no work intent gets a lower
# generation cap on Bonsai (see bonsai_llm.max_tokens_override) so "cool, ill
# grab some row cover" cannot cost 69s of reasoning. Deliberately narrow: any
# work word, any number, any question about the office, any named shot, any
# task/board turn keeps the full budget. Thinking stays ON either way.
_QUICK_WORK_RE = re.compile(
    r"\\b(?:write|draft|plan|fix|build|code|email|emails|campaign|ad|ads|post|"
    r"caption|prompt|script|shot|scene|render|image|video|search|look\\s*up|"
    r"check|report|number|numbers|price|pricing|margin|cost|budget|order|orders|"
    r"sales|store|site|website|customer|customers|product|products|list|"
    r"explain|analy[sz]e|compare|review|research|why|how\\s+(?:do|does|would|"
    r"should|can|much|many)|what\\s+(?:is|are|should|would|do|does)|should\\s+(?:i|we)|"
    r"tell\\s+me|show\\s+me|give\\s+me|help\\s+me|can\\s+you|could\\s+you|"
    r"delegate|brief|approve|schedule|undo|update|restart|deploy|test)\\b", re.I)
QUICK_REPLY_MAX_CHARS = 140
QUICK_REPLY_MAX_TOKENS = 1200


def _quick_reply_ask(message: str) -> bool:
    m = (message or "").strip()
    if not m or len(m) > QUICK_REPLY_MAX_CHARS:
        return False
    if re.search(r"\\d{2,}", m):
        return False
    if _QUICK_WORK_RE.search(m):
        return False
    return True''',
    ),
    (
        '''        if req.agent_id == ENGINEER_ID and not (req.personal or req.reply_to):
            bonsai_llm.tool_rounds_override.set(8)

        tool_call_log: list = []''',
        '''        if req.agent_id == ENGINEER_ID and not (req.personal or req.reply_to):
            bonsai_llm.tool_rounds_override.set(8)

        # QUICK REPLY cap for short casual messages -- see _quick_reply_ask.
        # Never on task/board turns, never on a named shot, never on an
        # office-condition question to Sophie.
        _quick = (not req.task and _quick_reply_ask(req.message)
                  and not (req.agent_id == MOVIE_ID and _names_a_shot)
                  and not (req.agent_id == ENGINEER_ID and _health_ask(req.message)))
        if _quick:
            bonsai_llm.max_tokens_override.set(QUICK_REPLY_MAX_TOKENS)
            bonsai_llm.quick_reply.set(True)
            print(f"[quick-reply] {agent['office_name']}: cap {QUICK_REPLY_MAX_TOKENS} :: {req.message[:60]!r}")

        tool_call_log: list = []''',
    ),
])

patch("agents.py", [
    (
        '''    "THINK LONG, ANSWER SHORT. However much reasoning a question takes, the "''',
        '''    # 2026-09-08 (Barry: "build the reasoning budget thing for short
    # messages"). Measured: this line in the SYSTEM prompt halves reasoning
    # on casual talk (1,867 -> 850 chars in the probe); in the user turn it
    # did nothing. Static, so it never busts the prompt cache.
    "MATCH YOUR THINKING TO THE MESSAGE. A casual line, a thank-you, a quick "
    "yes-or-no, small talk -- think for a few lines and answer; save the "
    "deep, careful reasoning for real questions and real problems, where it "
    "earns its keep. "
    "THINK LONG, ANSWER SHORT. However much reasoning a question takes, the "''',
    ),
])
print("done")
