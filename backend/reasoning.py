"""Reasoning upgrades (2026-09-15, Barry: "do them all... reasoning and logic
is #1 to me"). Three mechanisms, all on the WORK channel only, none on the
home channel, none on Elliot's shot / scene / full-write paths.

1. DEEP THINK -- adaptive self-consistency. On a deep-think ask the seat
   answers the same message three times independently (sampling varies the
   path), then judges its own three drafts: where they agree is settled,
   where they disagree it decides from evidence and says why. Measured gain
   for small models is 9-15 points on hard questions; the cost is ~4x the
   turn, so it is a MODE Barry invokes, not a default.
2. CROSS-CHECK -- one seat verifies another's numbers or claims before the
   answer reaches Barry. The literature is clear that a model is bad at
   auditing its own answer; a second seat with a different job is the check
   that works. Amara audits Victor's figures on decision asks; Marcus audits
   Derek's product claims on copy asks. The verdict is appended VERBATIM.
3. COUNCIL -- for one-way-door decisions asked of Victor (lease, hire, loan,
   rebrand, shut down...). Amara (numbers-first), Marcus (risk-first) and
   Derek (customer-first) each give a position independently -- diversity of
   METHOD is what makes debate help, and same-model-same-method debate
   regresses -- then Victor writes the decision memo. One round, no back and
   forth (long debates drift).

Cross-seat calls go through /api/chat with task:true (history-free, full
seat, tools on, nothing logged to any thread), the same door the board uses.
Every run is written to data/reasoning/ so Barry can read the drafts.
"""
from __future__ import annotations

import json
import os
import re
import time

import httpx

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(REPO, "data", "reasoning")
CHAT_URL = "http://127.0.0.1:8420/api/chat"
SEAT_TIMEOUT = 900.0

# ---------------------------------------------------------------- triggers
DEEP_RE = re.compile(
    r"\b(?:think\s+(?:it|this|that)\s+through|think\s+(?:hard|deeply|carefully|properly)"
    r"(?:\s+(?:about|on)\s+(?:it|this))?|deep[\s-]?think|three\s+ways|reason\s+(?:it|this)\s+out|"
    r"work\s+(?:it|this)\s+(?:through|out)\s+(?:properly|carefully|fully)|"
    r"double[\s-]?check\s+your\s+(?:reasoning|logic|math|numbers))\b|/deep\b", re.I)

# A decision ask: the answer is a call, not a fact.
DECISION_RE = re.compile(
    r"\b(?:should\s+(?:we|i)|can\s+we\s+afford|is\s+it\s+worth|worth\s+it|do\s+we\s+(?:go|do|move|buy|take)|"
    r"go\s+ahead|how\s+much\s+(?:should|can|could)\s+(?:we|i)|what\s+would\s+you\s+(?:do|recommend)|"
    r"recommend|which\s+(?:one|option|way)|decide|your\s+call|make\s+the\s+call)\b", re.I)
MONEY_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?|\b\d+(?:\.\d+)?\s?%")

# Product-claim words in a marketing reply (the Microlife-email class).
CLAIM_RE = re.compile(
    r"\b(?:\d+(?:\.\d+)?\s?%|yield|increase[sd]?|boost[s]?|guarantee[sd]?|proven|clinical(?:ly)?|"
    r"doubles?|triples?|fastest|best\s+in|#1|number\s+one|cures?|prevents?|eliminates?)\b", re.I)
COPY_ASK_RE = re.compile(r"\b(?:ad|ads|email|emails|post|caption|copy|headline|campaign|blurb|description|"
                         r"landing\s+page|subject\s+line|tagline|slogan|flyer)\b", re.I)

# One-way doors: hard or impossible to undo.
ONE_WAY_RE = re.compile(
    r"\b(?:sign(?:ing)?\s+(?:the|a|this)\s+(?:lease|contract|deal|agreement)|(?:a|the)\s+lease|lease\s+(?:a|the)|"
    r"hire|hiring|fire\s+(?:him|her|them)|let\s+(?:him|her|them)\s+go|buy\s+(?:the|a|this)\s+(?:building|store|shop|"
    r"warehouse|property|truck|van)|(?:take|get)\s+(?:the|a|out\s+a)\s+loan|invest(?:ing)?\s+(?:in|\$)|rebrand|"
    r"shut\s+(?:it\s+)?down|close\s+(?:the|down\s+the)\s+(?:store|shop|business)|launch(?:ing)?\s+(?:the|a|our)|"
    r"commit(?:ting)?\s+to|partner(?:ship)?\s+with|exclusive|wholesale\s+(?:deal|agreement)|"
    r"go\s+all\s+in|bet\s+the|spend\s+\$?\s?\d{1,3}(?:,\d{3})+|spend\s+\$?\s?\d{4,})\b", re.I)
COUNCIL_WORD_RE = re.compile(r"\b(?:council\s+(?:this|it)|run\s+(?:it|this)\s+by\s+the\s+team|"
                             r"(?:get|want)\s+the\s+team'?s\s+take|team\s+review|"
                             r"what\s+does\s+(?:the\s+)?(?:team|everyone)\s+think)\b", re.I)


# BIG THINK (Barry, 2026-09-15): his own words for "this one needs a sound
# answer" lift the per-message thinking budget to unlimited for that turn --
# a single pass that thinks as long as it needs. Deep think (above) is the
# heavier tool: three passes plus a judge, also at the unlimited budget.
BIG_THINK_RE = re.compile(
    r"\b(?:figure\s+(?:it|this|that|out)|figure\s+out|make\s+sure\s+(?:this|it|that)(?:'s|\s+is)\s+(?:right|correct)|"
    r"(?:a\s+)?sound\s+(?:answer|response|call)|be\s+(?:certain|sure)\s+(?:about|of|on)|"
    r"get\s+(?:this|it)\s+right|think\s+hard(?:er)?|really\s+think|no\s+guessing|"
    r"work\s+(?:it|this)\s+out|do\s+the\s+math|run\s+the\s+numbers)\b", re.I)


def is_deep_ask(message: str) -> bool:
    return bool(DEEP_RE.search(message or ""))


def is_big_think_ask(message: str) -> bool:
    return bool(BIG_THINK_RE.search(message or ""))


def needs_number_check(message: str, reply: str) -> bool:
    """Victor made a call with figures in it."""
    return bool(DECISION_RE.search(message or "")) and len(MONEY_RE.findall(reply or "")) >= 2


def needs_claim_check(message: str, reply: str) -> bool:
    """Derek wrote customer-facing copy carrying a product claim."""
    return bool(COPY_ASK_RE.search(message or "")) and len(CLAIM_RE.findall(reply or "")) >= 1


def is_council_ask(message: str) -> bool:
    m = message or ""
    return bool(COUNCIL_WORD_RE.search(m)) or (bool(ONE_WAY_RE.search(m)) and bool(DECISION_RE.search(m)))


# ---------------------------------------------------------------- helpers
def _stamp() -> str:
    return time.strftime("%Y-%m-%d_%H%M%S")


def _write_log(kind: str, payload: dict) -> str:
    os.makedirs(LOG_DIR, exist_ok=True)
    path = os.path.join(LOG_DIR, f"{kind}_{_stamp()}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    return path


async def ask_seat(agent_id: str, message: str) -> str:
    """A history-free task turn on another seat (full persona, brain, tools;
    nothing logged). Returns the reply text, or '' on failure -- a check
    that cannot run must never cost Barry the original answer."""
    try:
        async with httpx.AsyncClient(timeout=SEAT_TIMEOUT) as cx:
            r = await cx.post(CHAT_URL, json={"agent_id": agent_id, "message": message, "task": True,
                                                   "activity": "deep-think / council on your ask"})
        r.raise_for_status()
        reply = ((r.json() or {}).get("reply") or "").strip()
        if reply.startswith("[") and "GPU" in reply[:120]:
            return ""            # render guard answered, not the seat
        return reply
    except Exception as exc:  # noqa: BLE001
        print(f"[reasoning] ask_seat({agent_id}) failed: {exc}")
        return ""


# ---------------------------------------------------------------- 1. deep think
JUDGE_INSTRUCTION = (
    "\n\n[DEEP THINK -- you answered this same message THREE times independently; the "
    "three drafts are below. Read them as an auditor, not an author. Where they agree, "
    "that is settled. Where they disagree, decide from the evidence and the arithmetic "
    "which one is right and say why in one line -- do not average them and do not pick "
    "the longest. If all three share a mistake you can now see, name it and correct it. "
    "Then give ONE final answer in your normal voice. Do not mention drafts or attempts "
    "to him; the check is yours, the answer is his.]\n"
)


async def deep_think(run_once, run_judge, n: int = 3) -> tuple[str, dict]:
    """run_once() -> reply (same seat, same message, tools as usual).
    run_judge(extra_user_text) -> reply (same seat, tools off).
    Returns (final_reply, record)."""
    t0 = time.monotonic()
    drafts = []
    for i in range(n):
        d = (await run_once() or "").strip()
        drafts.append(d)
        print(f"[deep-think] draft {i+1}/{n}: {len(d)} chars")
    good = [d for d in drafts if d and not d.startswith("[")]
    if len(good) < 2:
        final = good[0] if good else (drafts[0] if drafts else "")
        rec = {"drafts": drafts, "judged": False, "secs": round(time.monotonic() - t0, 1)}
        _write_log("deepthink", rec)
        return final, rec
    block = JUDGE_INSTRUCTION + "\n".join(
        f"--- DRAFT {i+1} ---\n{d}\n" for i, d in enumerate(good))
    final = (await run_judge(block) or "").strip()
    if not final or final.startswith("["):
        final = good[0]
        judged = False
    else:
        judged = True
    rec = {"drafts": drafts, "final": final, "judged": judged,
           "secs": round(time.monotonic() - t0, 1)}
    path = _write_log("deepthink", rec)
    print(f"[deep-think] judged={judged} in {rec['secs']}s -> {os.path.basename(path)}")
    return final, rec


# ---------------------------------------------------------------- 2. cross-check
NUMBER_CHECK_BRIEF = (
    "OFFICE CROSS-CHECK. Barry asked Victor:\n\"{question}\"\n\nVictor answered:\n\"\"\"\n{reply}\n\"\"\"\n\n"
    "Your job, from the finance seat, before this reaches Barry: audit every figure in Victor's "
    "answer. For each number say where it comes from (a live tool result you fetched now, a fact "
    "in the brain, or nowhere), whether the arithmetic holds, and whether the conclusion follows "
    "from the numbers. Use your tools to pull the real figures. Do not re-answer the question. "
    "Reply in under 150 words, plain, starting with one of: CHECKS OUT / ONE PROBLEM / DOES NOT HOLD. "
    "Name the problem and the correct figure if you can. No hedging."
)
CLAIM_CHECK_BRIEF = (
    "OFFICE CROSS-CHECK. Barry asked Derek for copy:\n\"{question}\"\n\nDerek wrote:\n\"\"\"\n{reply}\n\"\"\"\n\n"
    "Your job, from the legal seat, before this reaches Barry: find every claim about a product or "
    "result in that copy (percentages, yield, 'proven', 'guaranteed', health or safety effects, "
    "comparatives). For each: substantiated by what we actually hold, or not; and whether it is a "
    "pesticide/health claim we must not make. Use read_product for the real product wording. Do not "
    "rewrite the copy. Under 150 words, starting with CLEAR / FIX BEFORE USE / DO NOT RUN, then the "
    "specific lines to change. No hedging."
)


async def cross_check(kind: str, checker_agent_id: str, checker_name: str,
                      question: str, reply: str) -> str:
    brief = (NUMBER_CHECK_BRIEF if kind == "numbers" else CLAIM_CHECK_BRIEF).format(
        question=question.strip()[:2000], reply=reply.strip()[:6000])
    t0 = time.monotonic()
    verdict = await ask_seat(checker_agent_id, brief)
    _write_log("crosscheck", {"kind": kind, "checker": checker_agent_id, "question": question,
                              "reply": reply, "verdict": verdict,
                              "secs": round(time.monotonic() - t0, 1)})
    if not verdict:
        return ""
    print(f"[cross-check] {checker_name} on {kind}: {verdict[:80]!r}")
    return f"\n\n--- {checker_name} checked the {kind} ---\n{verdict}"


# ---------------------------------------------------------------- 3. council
COUNCIL_SEATS = [
    ("business", "Amara", "the numbers: cost, margin, cash, break-even, what it does to runway"),
    ("legal", "Marcus", "the risk: what binds us, what we cannot undo, liability, what a lawyer would flag"),
    ("marketing", "Derek", "the customer: who this is for, whether they will notice or care, what it does to the brand"),
]
COUNCIL_BRIEF = (
    "OFFICE COUNCIL. Barry is weighing a decision he cannot easily undo:\n\"{question}\"\n\n"
    "Victor's first take:\n\"\"\"\n{draft}\n\"\"\"\n\n"
    "Answer from your lane ONLY -- {lane}. Use your tools for real figures. Give exactly three things, "
    "under 150 words total: (1) your position in one line: DO IT / DON'T / NOT YET, (2) your single "
    "strongest reason with the number or fact it rests on, (3) what would change your mind. "
    "Disagree with Victor if the evidence says so. No hedging, no summary of the others."
)
SYNTHESIS_INSTRUCTION = (
    "\n\n[COUNCIL -- three seats have answered independently from their own lanes; their positions are "
    "below. Write the DECISION MEMO for Barry: RECOMMENDATION (one line: do it / don't / not yet, and "
    "under what condition), THE NUMBER IT RESTS ON (one figure and its source), WHAT WOULD MAKE IT WRONG, "
    "and WHO DISAGREED AND WHY (name them). Where they conflict, decide -- do not split the difference. "
    "Keep it under 250 words. The three positions will be shown under your memo, so do not repeat them.]\n"
)


async def council(question: str, victor_draft: str, run_synthesis) -> tuple[str, dict]:
    """run_synthesis(extra_user_text) -> Victor's reply (same seat, tools off)."""
    t0 = time.monotonic()
    positions = []
    for agent_id, name, lane in COUNCIL_SEATS:
        brief = COUNCIL_BRIEF.format(question=question.strip()[:2000],
                                     draft=(victor_draft or "").strip()[:4000], lane=lane)
        text = await ask_seat(agent_id, brief)
        positions.append({"agent_id": agent_id, "name": name, "position": text})
        print(f"[council] {name}: {(text or '(no answer)')[:70]!r}")
    got = [p for p in positions if p["position"]]
    if len(got) < 2:
        rec = {"question": question, "draft": victor_draft, "positions": positions,
               "memo": "", "secs": round(time.monotonic() - t0, 1)}
        _write_log("council", rec)
        return victor_draft, rec
    block = SYNTHESIS_INSTRUCTION + "\n".join(
        f"--- {p['name']} ---\n{p['position']}\n" for p in got)
    memo = (await run_synthesis(block) or "").strip()
    if not memo or memo.startswith("["):
        memo = victor_draft
    shown = "\n\n".join(f"{p['name']}: {p['position']}" for p in got)
    final = f"{memo}\n\n--- The council ---\n{shown}"
    rec = {"question": question, "draft": victor_draft, "positions": positions,
           "memo": memo, "secs": round(time.monotonic() - t0, 1)}
    path = _write_log("council", rec)
    print(f"[council] memo in {rec['secs']}s -> {os.path.basename(path)}")
    return final, rec
