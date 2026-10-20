"""THE WORK CLAIM NET (2026-09-24) -- one check for every seat.

Research (docs/reliability-research-2026-09-24.md, item 1): the proven fix for agents bluffing is a
check IN CODE of every "I sent / I searched / I pulled the numbers" claim against the real tool log --
self-review without outside evidence was measured to make things worse. The office already had
seat-specific nets built after real bluffs (Sophie's read/save net, Vivian's photo net, the look net,
the lesson net, the hand-off net in main.py). This generalises the SAME shape to every work seat for
the claims none of them covered:
  a first-person claim in the reply + none of the backing tools in this turn's tool log
  -> ONE re-run with the fact in front of the agent -> still claiming -> an "(Office correction: ...)"
  line is added. The agent's words are never rewritten (Barry: tell them, don't alter them).
A rule only fires if the seat actually HAS one of the backing tools this turn, so the re-run can
always fix it. Work turns only -- home is not policed here.
"""
import re

_I = r"\bi(?:'ve|\s+have|\s+just)?\s+"
_OUR = r"(?:the\s+|our\s+|your\s+|his\s+)?(?:live\s+|latest\s+|current\s+|real\s+|recent\s+)?"

RULES = [
    ("sent_file",
     re.compile(_I + r"(?:sent|dropped|put|placed|uploaded|delivered|saved)\s+(?:it|this|that|them|"
                r"(?:the|a|an)\s+[\w-]+(?:\s+[\w-]+){0,2})\s+(?:to|on|in|into|onto)\s+your\s+"
                r"(?:desk|out\s*box|inbox|files?)\b"
                r"|\b(?:it'?s|it\s+is|they'?re|they\s+are)\s+(?:now\s+)?(?:on|in)\s+your\s+desk\b", re.I),
     ("send_file_to_barry",),
     "you told Barry a file is on his desk, but send_file_to_barry was never called"),
    ("web",
     re.compile(_I + r"(?:searched|looked\s+(?:it|this|that)\s+up|checked)\s+"
                r"(?:online|on\s+the\s+web|the\s+web|the\s+internet|on\s+the\s+internet)\b"
                r"|\baccording\s+to\s+(?:my|a|the)\s+(?:web\s+)?search\b"
                r"|\bmy\s+(?:web\s+|quick\s+)?search\s+(?:shows|showed|found|turned\s+up|says)\b", re.I),
     ("search_web", "browse_site", "browse_gotchoback"),
     "you said you searched online, but no search or browse tool was called"),
    ("store",
     re.compile(_I + r"(?:pulled|checked|looked\s+at|ran|reviewed|went\s+through)\s+" + _OUR +
                r"(?:sales|orders|revenue|store\s+(?:data|numbers|report)|inventory|stock\s+levels?|"
                r"catalog(?:ue)?|product\s+(?:page|listing|data))\b", re.I),
     ("sales_summary", "what_is_selling", "lookup_product", "read_product", "browse_site", "buyer_sources"),
     "you said you pulled the store's numbers or product data, but no store tool was called"),
    ("ads",
     re.compile(_I + r"(?:pulled|checked|looked\s+at|reviewed|went\s+through)\s+" + _OUR +
                r"(?:ads?\b|ad\s+(?:data|numbers|report|performance)|campaigns?\b|microsoft\s+ads)", re.I),
     ("ads_summary",),
     "you said you checked the ads, but ads_summary was never called"),
    ("email",
     re.compile(_I + r"(?:checked|looked\s+at|pulled|reviewed)\s+" + _OUR +
                r"(?:omnisend|email\s+list|subscribers?|automations?|email\s+flows?)\b", re.I),
     ("check_omnisend",),
     "you said you checked Omnisend, but check_omnisend was never called"),
    ("site",
     re.compile(_I + r"(?:checked|looked\s+at|browsed|visited|went\s+(?:to|through)|pulled\s+up)\s+" + _OUR +
                r"(?:site|website|storefront|blog|home\s*page|gotcho\s*back(?:\.com)?|bdubbgrowsllc(?:\.com)?)\b", re.I),
     ("browse_site", "browse_gotchoback"),
     "you said you looked at the website, but browse_site was never called"),
    ("saved",
     re.compile(r"\b(?:I'?ve|I have|I)\s+(?:saved|stored|noted|written|logged)\b[^.]{0,50}\b(?:note|notes|brain|memory)\b"
                r"|\bin my notes\b|\b(?:saved|logged) (?:it|this|that) (?:to|in) (?:my )?(?:notes|memory|brain)\b", re.I),
     ("save_note", "remember_lesson", "update_business_brain"),
     "you said you saved a note, but no save tool was called"),
]

# SOPHIE'S DONE-CLAIMS (2026-10-10, Barry: "dont let Sophie be delusional"). Her 14:34 turn ran out of time after
# 7 rounds of READS; the forced answer said "**Restarted the backend.**" and "Raised the dithering threshold from
# 7 to 12" -- neither happened (watchdog.log: no restart; bonsai_llm.py still 7). Bullet-style claims with no "I"
# are caught too. 5th field = the seat tool that makes the rule apply; the backing entry is narrower:
# "restart_backend:scheduled" is logged only when a restart was actually scheduled (bonsai_llm tool loop).
_CLAIM_START = r"(?:^|[\n*•-]\s*|\bI(?:'ve|\s+have|\s+just|\s+also)?\s+|\band\s+(?:I\s+)?)(?:\*\*)?"
RULES += [
    ("restart",
     re.compile(_CLAIM_START + r"restart(?:ed|ing)\s+(?:the\s+)?(?:backend|office|server|stack|bonsai)\b", re.I | re.M),
     ("restart_backend:scheduled",),
     "you said the backend/office was restarted, but restart_backend was never run (or was refused) this turn",
     ("restart_backend",)),
    ("code_change",
     re.compile(_CLAIM_START + r"(?:raised|lowered|changed|tuned|patched|edited|rewrote|modified|bumped|set)\s+"
                r"(?:the\s+|a\s+|its\s+|my\s+)?[\w .'-]{0,40}?(?:threshold|code|file|setting|limit|cap|config|"
                r"function|value|stopper|detector|window|timeout|ceiling|\.py)\b", re.I | re.M),
     ("propose_code_fix", "submit_agent_fix", "run_command"),
     "you said you changed code or a setting, but no code-fix or command tool ran this turn (a proposal "
     "is not a change until Barry approves it)",
     ("propose_code_fix", "run_command")),
]

# ILNORA'S "NOW BUILDING" (2026-10-11, Barry: "see if she is really doing it"). Three replies in a row said "Now
# building the rewrite ... Running the word-count gate first" with ZERO tool calls -- her old reply echoing -- while
# the draft sat unsent. A video "built / sent / queued / checked" claim needs a video tool in this turn's log.
RULES += [
    ("video_action",
     re.compile(r"\b(?:now building|building (?:it|the (?:video|rewrite|short|long))(?: now)?|"
                r"(?:i(?:'ve|\s+have|\s+just)?\s+)?(?:sent|queued|submitted) (?:it|the (?:video|draft|rewrite))|"
                r"it'?s (?:now )?(?:queued|in the queue|building)|running the (?:word.count gate|check)|"
                r"sending it now|send(?:ing)? it to the queue)\b", re.I),
     ("video_draft", "make_video", "check_video"),
     "you said the video is being built / sent / checked, but no video tool (video_draft, make_video, check_video) "
     "ran this turn -- call it now, or say plainly that it is not sent",
     ("video_draft", "make_video")),
]
BASE_TOOLS = {"read_skill", "inspect_brain", "look_at_my_pictures", "save_note"}


def roster(extra_tools: list | None, web: bool) -> set:
    names = {t["function"]["name"] for t in (extra_tools or []) if isinstance(t, dict) and "function" in t}
    return names | BASE_TOOLS | ({"search_web"} if web else set())


def gaps(reply: str, tool_log: list | None, seat_tools: set, skip: tuple = ()) -> list[str]:
    """Claims in `reply` that no call in `tool_log` backs. Empty = honest."""
    log = set(tool_log or [])
    out = []
    for rule in RULES:
        key, rx, tools, note = rule[:4]
        needs = rule[4] if len(rule) > 4 else tools
        if key in skip or not (set(needs) & seat_tools):
            continue
        if rx.search(reply or "") and not (set(tools) & log):
            out.append(note)
    return out


def note_for_rerun(found: list[str]) -> str:
    return ("\n\n[OFFICE CHECK -- your draft reply failed these checks: " + "; ".join(found) +
            ". The tools are real and were not called. Either call the tool now and write the reply "
            "from what it returns, or say plainly that you have not done it. Never claim a send, a "
            "search, a check or a save that no tool result shows.]")


def correction(found: list[str]) -> str:
    return ("\n\n(Office correction: " + "; ".join(found) +
            ". Treat that part as NOT DONE / UNVERIFIED and ask me to actually do it.)")


# ---------------------------------------------------------------- NUMBERS (2026-09-24)
# Research item 6: numbers come from tools or shown math, never from the model's head. Every money
# figure, percentage and business count in a work reply must be GROUNDED:
#   - found (to the cent / within 0.5%) in this turn's tool results, Barry's message, the conversation
#     or the always-on office facts in the system prompt, or
#   - ONE step (+ - x / , x% of, x% off/on) from two such numbers, or
#   - a step from an EARLIER grounded figure in the same reply (shown working chains).
# Same shape as the claims: one re-run, then an Office-correction line naming the figures.
import contextvars
import bisect

# The exact tool-result text the model saw this turn (bonsai_llm + llm_router append; main sets []).
tool_results: contextvars.ContextVar = contextvars.ContextVar("claim_net_tool_results", default=None)


def record_tool_result(text: str) -> None:
    lst = tool_results.get()
    if lst is not None:
        lst.append(text or "")


_NUM = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_MONEY_RE = re.compile(r"\$\s?" + _NUM)
_PCT_RE = re.compile(_NUM + r"\s?%")
_COUNT_RE = re.compile(_NUM + r"\s+(?:orders?|units?|clicks?|impressions?|visitors?|sessions?|subscribers?|"
                       r"customers?|sales|conversions?|views?|opens?|signups?|sign-ups?|bottles?|cases?)\b", re.I)
_ANY_NUM_RE = re.compile(r"(?<![\w.])" + _NUM)
_MONEY_OR_PCT_SRC_RE = re.compile(r"\$\s?" + _NUM + r"|" + _NUM + r"\s?%")


def _f(s: str) -> float:
    return float(s.replace(",", ""))


def _reply_figures(reply: str) -> list[tuple[int, str, float]]:
    """(position, as written, value) for every money / % / business-count figure, in reply order."""
    out = {}
    for rx in (_MONEY_RE, _PCT_RE, _COUNT_RE):
        for m in rx.finditer(reply or ""):
            v = _f(m.group(1))
            if rx is _COUNT_RE and v <= 10:          # "3 orders" style small counts are not the risk
                continue
            if rx is _PCT_RE and v in (0, 100):
                continue
            out[m.start()] = (m.start(), m.group(0).strip(), v)
    return [out[k] for k in sorted(out)]


class _Pool:
    """Sorted grounded values with a cent / 0.5% tolerance lookup."""
    def __init__(self):
        self.vals: list[float] = []
        self._sorted = True

    def add(self, v: float):
        if v == v and abs(v) < 1e12:                # skip NaN / absurd
            self.vals.append(round(v, 6))
            self._sorted = False

    def has(self, v: float) -> bool:
        if not self._sorted:                        # sort once per batch of adds, not per add
            self.vals.sort()
            self._sorted = True
        tol = max(0.011, abs(v) * 0.005)
        i = bisect.bisect_left(self.vals, v - tol)
        return i < len(self.vals) and self.vals[i] <= v + tol


def _derive(a: float, b: float):
    yield a + b; yield a - b; yield b - a; yield a * b
    if b: yield a / b
    if a: yield b / a
    yield a * b / 100; yield a * (1 - b / 100); yield a * (1 + b / 100)
    yield b * (1 - a / 100); yield b * (1 + a / 100)
    if b: yield a / b * 100
    if a: yield b / a * 100


def number_gaps(reply: str, sources: list[str], base_sources: list[str], max_base: int = 80) -> list[str]:
    """Figures in `reply` that nothing grounds. `sources` = every text the agent had (system prompt,
    conversation, tool results); `base_sources` = the texts whose numbers may be combined (tool results,
    Barry's message, the conversation) -- plus the money/% facts of the system prompt."""
    figs = _reply_figures(reply)
    if not figs:
        return []
    exact = _Pool()
    for t in sources:
        for m in _ANY_NUM_RE.finditer(t or ""):
            try:
                exact.add(_f(m.group(1)))
            except ValueError:
                pass
    base: list[float] = []
    for t in base_sources:
        for m in _ANY_NUM_RE.finditer(t or ""):
            try:
                base.append(_f(m.group(1)))
            except ValueError:
                pass
    for t in sources[:1]:                           # the system prompt: only its money / % facts
        for m in _MONEY_OR_PCT_SRC_RE.finditer(t or ""):
            base.append(_f(m.group(1) or m.group(2)))
    base = list(dict.fromkeys(v for v in base if v != 0))[:max_base]
    derived = _Pool()
    for i, a in enumerate(base):
        for b in base[i:]:
            for v in _derive(a, b):
                derived.add(v)
    ungrounded = []
    for _, text, v in figs:
        if exact.has(v) or derived.has(v):
            ok = True
        else:
            ok = False
        if ok:                                       # a grounded figure can feed the next step
            for b in base:
                for d in _derive(v, b):
                    derived.add(d)
            # ...including a two-cost line: "$57.80 minus $41 cost and $10 shipping = $6.80"
            for i, b in enumerate(base):
                for c in base[i:]:
                    derived.add(v - b - c)
                    derived.add(v + b + c)
                    derived.add(v - b + c)
                    derived.add(v + b - c)
            base.append(v)
        else:
            ungrounded.append(text)
    return list(dict.fromkeys(ungrounded))


def number_note_for_rerun(figs: list[str]) -> str:
    return ("\n\n[OFFICE CHECK -- these figures in your draft have no source this turn: " + ", ".join(figs) +
            ". Every number must come from a tool result (sales_summary, what_is_selling, lookup_product, "
            "read_product, ads_summary...), from Barry's own message, or from math you SHOW step by step "
            "on those numbers. Call the tool now, show the working, or leave the figure out -- never estimate "
            "a number and state it as fact.]")


def number_correction(figs: list[str]) -> str:
    return ("\n\n(Office correction: no source this turn for " + ", ".join(figs) +
            ". Treat those figures as UNVERIFIED -- ask me to pull the real numbers.)")
