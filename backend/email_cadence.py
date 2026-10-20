"""DEREK'S WEEKLY EMAILS -- two a week, four kinds in rotation, two phases.

Barry, 2026-09-01: "i want him to send two types of email every week. once i
see that he can make good campaigns and emails, ill let him go free to do what
he wants, but only twice a week max." Types: "all 3" of the offered bundles,
which is four distinct kinds. Days: Wednesday and Saturday.

THE TWO PHASES, ONE SETTING APART:
  PHASE 1 (default, `email_autonomy` = false): Derek drafts on the clock, the
     draft lands in Barry's Out box as an `email` approval with its send time
     and audience already attached. Barry clicks approve; dispatch sends (or
     schedules). Nothing leaves without the click.
  PHASE 2 (`email_autonomy` = true, flipped ONLY by Barry in words): the same
     draft is approved by the office and dispatched immediately. Still capped
     at two a week (dispatch counts real sends), still segment-targeted, still
     dead under Offline Mode. Nothing in this file can turn phase 2 on.

WHY SATURDAY WORKS WITH THE OFFICE CLOSED: the draft is written on a workday
(clock.py: Mon-Fri 9-6) and the send is SCHEDULED inside Omnisend, on their
servers. The PC can be off Saturday morning; the email still goes.

WHY THE DRAFT GOES THROUGH /api/chat AND NOT A BARE MODEL CALL: /api/chat is
where Derek's whole seat lives -- persona, brain, recall, the store tools and
check_omnisend. A bare generate() would hand him none of that and he would
write a generic newsletter. The `task` flag keeps the exchange out of his
conversation thread and away from the standing-rule scanner.

State: data/email_cadence_state.json (which slots have been drafted). Log:
data/email_cadence.log. Manual trigger for a test: `draft_now(kind)`.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import os
import re

import httpx

import clock
import content_policy
import dispatch
import email_design
import factcheck
import ideation
import memory

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STATE = os.path.join(_ROOT, "data", "email_cadence_state.json")
_LOG = os.path.join(_ROOT, "data", "email_cadence.log")

AGENT_ID = "marketing"
CHECK_EVERY_SECONDS = 15 * 60
STARTUP_DELAY_SECONDS = 180
DRAFT_LEAD_HOURS = 48              # how far ahead of the send a draft may be made
AUTONOMY_KEY = "email_autonomy"

# Send slots: (weekday, hour). Monday=0. Barry 2026-09-01: "Wednesday and Saturday";
# Barry 2026-09-26: "we should run emails twice a week, wed, and sunday".
SLOTS = ((2, 10), (6, 10))

# The four kinds, in rotation. Two slots a week -> each kind lands every other
# week. Order chosen so a week never carries two sells back to back.
KINDS = ("grower-tip", "product-feature", "store-news", "reorder-reminder")

_BRIEFS = {
    "grower-tip": (
        "This week's email is a GROWER TIP -- educational, no offer, no codes. "
        "One real problem growers hit this time of year (feeding, medium, EC/pH "
        "drift, light, pests -- pick one) and how to handle it, grower to grower. "
        "You may name a product from the store only where it genuinely solves "
        "the problem, with its live price from lookup_product; if it is out of "
        "stock, do not feature it."),
    "product-feature": (
        "This week's email is a PRODUCT FEATURE. Pick ONE product from the store "
        "that is in stock (use lookup_product -- live price, photo URL, link) and "
        "write why a grower would want it, what it pairs with, and who it is NOT "
        "for. Put it (and anything it pairs with) in PRODUCTS: -- Vivian's design "
        "shows the real photo, the live price and the link from the store, so you "
        "never type a price or a photo URL. If it is Bionova, the code is "
        "BIG15 (Bionova only, first order); otherwise BIG10 (everything except "
        "Bionova, first order). Whichever you use, the footnote MUST appear: "
        "'To get both discounts, use the codes separately - they can't be "
        "combined on the same order.'"),
    "store-news": (
        "This week's email is STORE NEWS -- what is new or back in stock, a recent "
        "blog post worth reading, anything changing at the store. Use browse_site "
        "and lookup_product so every claim is real; if nothing is genuinely new, "
        "say what is in season instead. No offer unless one genuinely fits."),
    "reorder-reminder": (
        "This week's email is a REORDER REMINDER aimed at past Bionova buyers. "
        "Nutrients run out on a cycle -- remind them plainly, with the live price "
        "and link for the base nutrient (lookup_product), and BIG15 with its "
        "footnote: 'To get both discounts, use the codes separately - they can't "
        "be combined on the same order.' Warm, short, no pressure."),
}

_FORMAT = (
    # Barry, 2026-09-01: "he needs to read all the product descriptions before
    # writing anything." Stated in the brief every time, not left to memory.
    "\n\nBEFORE YOU WRITE: for EVERY product you are going to name, call "
    "read_product and read its full description as it stands on the site. "
    "What you say about a product must come from that description -- its "
    "actual use, feeding rates, sizes, what it pairs with -- never from what "
    "you assume the product is. If you have not read it, you do not mention it. "
    "For a product feature, read the description of the product you pick AND "
    "the products you say it pairs with."
    # 2026-09-26, Barry: "derek comes up with email posts, products coupons, tips, etc and
    # vivian comes up with style and design." Derek now hands over a CONTENT SHEET (his words,
    # products, coupon, button); Vivian designs it in Omnisend's blocks (email_design.py).
    "\n\nYOU WRITE IT, VIVIAN DESIGNS IT. You decide what this email is -- the "
    "tip, the products, the coupon, every word, the button. Vivian decides how it "
    "looks. Sign the last section off as Barry.\n\n"
    + email_design.SHEET_FORMAT
)


def _log(msg: str) -> None:
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(f"[email-cadence] {msg}")
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
    os.makedirs(os.path.dirname(_STATE), exist_ok=True)
    tmp = _STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, _STATE)


def is_autonomous() -> bool:
    return memory.get_setting(AUTONOMY_KEY, "false") == "true"


def upcoming_slots(now: datetime.datetime | None = None, days: int = 8):
    """(send_at, slot_index) for every slot in the next `days` days."""
    now = now or datetime.datetime.now()
    out = []
    for ahead in range(0, days):
        day = (now + datetime.timedelta(days=ahead)).date()
        for idx, (wd, hour) in enumerate(SLOTS):
            if day.weekday() == wd:
                send_at = datetime.datetime.combine(day, datetime.time(hour, 0))
                if send_at > now:
                    out.append((send_at, idx))
    return sorted(out)


def kind_for(send_at: datetime.datetime, slot_idx: int) -> str:
    week = send_at.isocalendar()[1]
    return KINDS[(week * len(SLOTS) + slot_idx) % len(KINDS)]


def _slot_key(send_at: datetime.datetime) -> str:
    return send_at.strftime("%Y-%m-%d-%H")


def _parse_reply(reply: str) -> tuple[str, str] | None:
    text = (reply or "").strip()
    # strip a ```html fence if the model wrapped it
    text = re.sub(r"^```(?:html)?\s*|\s*```$", "", text, flags=re.I | re.S).strip()
    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if len(lines) < 3:
        return None
    subject = lines[0].strip().lstrip("#").replace("**", "").strip()
    if subject.lower().startswith("subject:"):
        subject = subject[8:].strip()
    body = "\n".join(lines[1:]).strip()
    body = re.sub(r"^\s*<html>|</html>\s*$", "", body, flags=re.I).strip()  # tolerate a wrapper
    if not subject or len(body) < 80:
        return None
    return subject, body


_TOPIC_STOP = {
    "what", "your", "with", "that", "this", "from", "telling", "need", "needs", "extra", "about", "when", "into",
    "more", "less", "keep", "keeps", "they", "them", "their", "have", "will", "just", "why", "how", "grow", "grows",
    "growing", "grower", "growers", "plant", "plants", "here", "best", "ever", "every", "still", "back", "know",
    "make", "makes", "free", "shipping", "sale", "save", "week", "today", "season", "thing", "things", "check",
}


def _topic_words(text: str) -> set[str]:
    words = re.findall(r"[a-z]+", (text or "").lower().replace("’s", "").replace("'s", ""))
    return {w for w in words if len(w) >= 4 and w not in _TOPIC_STOP}


def _back_to_back(sheet: dict) -> tuple[str, list[str]]:
    """(previous subject, shared topic words) -- empty list when the topics differ."""
    try:
        with memory.get_db() as conn:
            row = conn.execute("SELECT content FROM approvals WHERE action_type = 'email' AND status NOT IN "
                               "('rejected', 'deleted') ORDER BY id DESC LIMIT 1").fetchone()
    except Exception:  # noqa: BLE001
        return "", []
    if not row or not (row[0] or "").strip():
        return "", []
    prev = row[0].strip().splitlines()[0][:120]
    new = " ".join(str(sheet.get(k) or "") for k in ("subject", "headline", "eyebrow"))
    return prev, sorted(_topic_words(prev) & _topic_words(new))


async def draft(kind: str, send_at: datetime.datetime) -> dict:
    """One draft, through Derek's full seat. Queues it; may auto-dispatch."""
    brief = _BRIEFS[kind]
    when = send_at.strftime("%A %B %d at %I:%M %p").replace(" 0", " ")
    # NO REPEATS (2026-10-02, Barry on #541 "Why coco grows need extra calcium": "we did the coco already", then:
    # "topics canbe the same, but not the same info. coco again is cool, just not back to back and not the same
    # images and info"). Derek sees the last 8 weeks of subjects, newest first, before he writes.
    try:
        since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(weeks=8)).isoformat()
        with memory.get_db() as _conn:
            _done = [r[0].strip().splitlines()[0][:120] for r in _conn.execute(
                "SELECT content FROM approvals WHERE action_type = 'email' AND created_at >= ? ORDER BY id DESC",
                (since,)) if (r[0] or "").strip()]
    except Exception:  # noqa: BLE001
        _done = []
    _recent = ("\n\nEMAILS ALREADY WRITTEN in the last 8 weeks, newest first:\n- " + "\n- ".join(dict.fromkeys(_done))
               + "\nA topic can come back, but never back to back with the newest one above, and never with the same "
                 "information or the same images -- bring a new angle, new facts and new pictures.") if _done else ""
    prompt = (
        f"Scheduled job from the office: your weekly email. It is due to go out "
        f"{when}. Check the account first (check_omnisend what='list') and "
        f"pull real product data before you write.\n\n{brief}"
        # Barry, 2026-09-18: "email and paid ads should be like this too."
        # Same content mix and the same Bionova priority as social -- one
        # definition in content_policy, imported by both cadences.
        f"{content_policy.MIX}{_FORMAT}{_recent}"
    )
    async with httpx.AsyncClient(timeout=1800) as cx:
        r = await cx.post("http://127.0.0.1:8420/api/chat",
                          json={"agent_id": AGENT_ID, "message": prompt, "task": True,
                                "activity": f"writing this week's email ({kind})"})
    r.raise_for_status()
    data = r.json() or {}
    reply = data.get("reply") or ""
    tool_calls = data.get("tool_calls") or []
    sheet = email_design.parse_sheet(reply)
    if not sheet:
        _log(f"{kind}: reply was not a content sheet ({len(reply)} chars) -- asking once more")
        async with httpx.AsyncClient(timeout=1800) as cx:
            r = await cx.post("http://127.0.0.1:8420/api/chat", json={
                "agent_id": AGENT_ID, "task": True,
                "message": prompt + "\n\n[OFFICE: your last answer was not a content sheet. Return ONLY "
                                    "the sheet, starting with SUBJECT: and ending with FOR VIVIAN:.]"})
        r.raise_for_status()
        data = r.json() or {}
        tool_calls = tool_calls + (data.get("tool_calls") or [])
        sheet = email_design.parse_sheet(data.get("reply") or "")
    if not sheet:
        _log(f"{kind}: still no content sheet -- skipped")
        return {"ok": False, "why": "unparseable", "reply": reply[:300]}
    # THE CONTENT BAR (2026-09-26, Barry: "theres no info about the product or a tip. just basic" /
    # "i need high Level every time"). One re-run with the exact gaps; still thin = the card says so.
    _names = [t if isinstance(t, str) else (t.get("name") if isinstance(t, dict) else str(t)) for t in tool_calls]
    gaps = email_design.sheet_gaps(sheet, kind, _names)
    if gaps:
        _log(f"{kind}: sheet below the bar ({'; '.join(gaps)[:200]}) -- sending it back once")
        async with httpx.AsyncClient(timeout=1800) as cx:
            r = await cx.post("http://127.0.0.1:8420/api/chat", json={
                "agent_id": AGENT_ID, "task": True,
                "message": prompt + "\n\n[OFFICE QUALITY BAR -- this sheet was NOT accepted, Barry wants high "
                                    "level every time. Fix exactly these: " + "; ".join(gaps)
                           + ". Read read_skill 'writing-the-email-content-sheet' if you have not. Return the "
                             "whole corrected sheet, SUBJECT: first.]"})
        r.raise_for_status()
        d2 = r.json() or {}
        s2 = email_design.parse_sheet(d2.get("reply") or "")
        if s2:
            tool_calls = tool_calls + (d2.get("tool_calls") or [])
            _names = [t if isinstance(t, str) else (t.get("name") if isinstance(t, dict) else str(t)) for t in tool_calls]
            sheet, gaps = s2, email_design.sheet_gaps(s2, kind, _names)
        _log(f"{kind}: after the re-run -> {('still: ' + '; '.join(gaps)) if gaps else 'meets the bar'}")
    # NOT BACK TO BACK (2026-10-02). Telling him was not enough: with the 8-week list in front of him, Derek redrafted
    # #541 (coco) as #542 "Coco's Calcium Cure" -- coco again, right after Wednesday's coco email. Barry: "coco again
    # is cool, just not back to back". So the office checks it: if this sheet shares its topic words with the
    # previous email (the newest one not turned down), it goes back to him with the reason -- up to twice.
    for _try in range(2):
        prev, shared = _back_to_back(sheet)
        if not shared:
            break
        _log(f"{kind}: same topic as the previous email '{prev}' ({', '.join(shared)}) -- sending it back")
        async with httpx.AsyncClient(timeout=1800) as cx:
            r = await cx.post("http://127.0.0.1:8420/api/chat", json={
                "agent_id": AGENT_ID, "task": True,
                "message": prompt + f"\n\n[OFFICE: NOT ACCEPTED -- the previous email was '{prev}', and this sheet is "
                                    f"on the same topic ({', '.join(shared)}). Barry: a topic can come back, but never "
                                    f"back to back. Pick a different topic and product focus, and return the whole "
                                    f"sheet, SUBJECT: first.]"})
        r.raise_for_status()
        d3 = r.json() or {}
        s3 = email_design.parse_sheet(d3.get("reply") or "")
        if not s3:
            break
        tool_calls = tool_calls + (d3.get("tool_calls") or [])
        sheet = s3
    _prev_last, _shared_last = _back_to_back(sheet)
    if _shared_last:
        # still the same topic after two send-backs -> never queued (2026-10-02: the gap was that it went out anyway)
        _log(f"{kind}: still the same topic as '{_prev_last}' ({', '.join(_shared_last)}) after two send-backs -- "
             f"NOT queued")
        return {"ok": False, "why": f"back-to-back topic ({', '.join(_shared_last)}) after two send-backs"}
    subject = sheet["subject"]
    content = email_design.sheet_text(sheet)

    # ONLY REAL STUFF (Barry, 2026-09-09, after #207 told customers Microlife
    # was back in stock while it was out): the draft is checked against the
    # LIVE store before it is queued. A draft written with no tool calls is
    # not accepted at all -- #207's trace was tool_calls [] despite the brief.
    # One re-run with the report in front of him; if it still fails it is
    # queued with the FACT-CHECK banner on top, which dispatch refuses to send.
    check = factcheck.check_email(content)
    if not tool_calls or not check["ok"]:
        why = ("You called NO tools -- nothing in this draft was read from the store. "
               if not tool_calls else "")
        _log(f"{kind}: draft rejected by fact-check "
             f"(tools={len(tool_calls)}, problems={len(check['problems'])}) -- re-running once")
        nudge = ("\n\n[OFFICE FACT-CHECK -- your draft was NOT accepted. " + why
                 + "Findings:\n" + factcheck.report(check)
                 + "\nRewrite it. Only real stuff, and only what is there: every product "
                   "you name must be read with read_product NOW and described as in stock "
                   "only if the store shows instock; say nothing about a 'new guide' unless "
                   "you link the real post from browse_site what='posts'; no percentages or "
                   "figures you did not read from the store or the offer codes. Return the "
                   "corrected email in the same format, subject line first.]")
        async with httpx.AsyncClient(timeout=1800) as cx:
            r2 = await cx.post("http://127.0.0.1:8420/api/chat",
                               json={"agent_id": AGENT_ID, "message": prompt + nudge, "task": True})
        r2.raise_for_status()
        data2 = r2.json() or {}
        sheet2 = email_design.parse_sheet(data2.get("reply") or "")
        if sheet2:
            sheet, subject = sheet2, sheet2["subject"]
            content = email_design.sheet_text(sheet)
            tool_calls = data2.get("tool_calls") or []
            check = factcheck.check_email(content)
        if not tool_calls or not check["ok"]:
            _log(f"{kind}: STILL failing after re-run -- queued with the fact-check banner")
            content = factcheck.banner(check) + content
        else:
            _log(f"{kind}: re-run passed the fact-check ({len(tool_calls)} tool calls)")
    aid = memory.queue_for_approval(AGENT_ID, "email", content)
    segment = memory.get_setting(dispatch.DEFAULT_SEGMENT_KEY, "") or ""
    with memory.get_db() as conn:
        conn.execute("UPDATE approvals SET send_at = ?, segment_id = ? WHERE id = ?",
                     (send_at.isoformat(timespec="minutes"), segment, aid))
    _log(f"{kind}: drafted -> approval {aid}, subject {subject[:60]!r}, "
         f"send_at {send_at:%Y-%m-%d %H:%M}, segment {segment or 'DEFAULT-NONE'}")
    email_design.save_sheet(aid, sheet)
    with open(os.path.join(email_design.draft_dir(aid), "content_gaps.json"), "w", encoding="utf-8") as _f:
        json.dump(gaps, _f)                       # shown on his card if Derek never cleared the bar

    # VIVIAN DESIGNS IT (2026-09-26) -- on her own seat, with her own design shelf and tools.
    designed = await design_with_vivian(aid, sheet, kind)
    result = {"ok": True, "approval_id": aid, "kind": kind, "subject": subject, "designed": designed}
    if is_autonomous() and designed:
        # PHASE 2 -- the office approves on Barry's standing say-so. Every
        # guard in dispatch still applies: cap, offline, segment, no double send.
        memory.decide_approval(aid, True)
        d = dispatch.dispatch_approved(aid)
        _log(f"{kind}: AUTONOMOUS dispatch of {aid} -> {d.get('status')}: "
             f"{str(d.get('detail'))[:160]}")
        result["dispatched"] = d
    return result


CREATIVE_ID = "creative"


async def design_with_vivian(aid: int, sheet: dict, kind: str) -> bool:
    """Barry's split: Derek decided WHAT the email is; Vivian decides how it LOOKS. She gets his
    sheet verbatim and designs it with design_email, looking at Omnisend's own render until it is
    right. Returns True when a design exists on the card."""
    pts = "\n".join(f"POINT {n}: {p['title']} | {p['text']}" for n, p in sorted(sheet.get("points", {}).items()))
    secs = "\n".join((f"HEADING {n}: {sheet['headings'][n]}\n" if sheet["headings"].get(n) else "")
                     + f"SECTION {n}: {sheet['sections'][n]}" for n in sorted(sheet["sections"]))
    ask = (
        f"Derek's email for this week is written -- a {kind.replace('-', ' ')}. It is draft #{aid}. "
        "Your part is the design: the style, the layout, the pictures, how it all looks. His words, "
        "products, coupon and button are his and are fixed; you place them, you do not rewrite them.\n\n"
        "Before you design, read read_skill 'how-vivian-designs-an-email' (the design format and the "
        "checklist) and 'email-design-that-sells' (layouts that work, like the ones Barry showed). "
        "If a real product is in it, look at its real photo (look_at_product_photo).\n\n"
        f"--- DEREK'S SHEET ---\nSUBJECT: {sheet.get('subject', '')}\nPREHEADER: {sheet.get('preheader', '')}\n"
        f"EYEBROW: {sheet.get('eyebrow', '')}\nHEADLINE: {sheet.get('headline', '')}\n"
        f"SUBHEAD: {sheet.get('subhead', '')}\nBANNER: {sheet.get('banner', '')}\n{secs}\n{pts}\n"
        f"PRODUCTS: {'; '.join(sheet.get('products', [])) or 'none'}\n"
        f"OFFER: {sheet.get('offer') or 'none'}  {sheet.get('offer_line', '')}\n"
        f"CTA: {sheet.get('cta_text', '')} -> {sheet.get('cta_link', '')}\n"
        f"FOR VIVIAN: {sheet.get('for_vivian', '')}\n--- END ---\n\n"
        f"Call design_email with draft_id {aid} and your design. LOOK at the screenshot it gives back "
        "and fix anything that is not right with another design_email call. When it is right, say in "
        "two or three sentences what you designed and why -- that is what Barry reads beside it."
    )
    try:
        async with httpx.AsyncClient(timeout=2400) as cx:
            r = await cx.post("http://127.0.0.1:8420/api/chat",
                              json={"agent_id": CREATIVE_ID, "message": ask, "task": True,
                                    "activity": f"designing Derek's email #{aid}"})
        r.raise_for_status()
        data = r.json() or {}
    except Exception as e:  # noqa: BLE001 -- a failed design still leaves his words on the card
        _log(f"#{aid}: Vivian's design turn failed ({type(e).__name__}: {e})")
        return False
    note = (data.get("reply") or "").strip()
    designed = os.path.exists(os.path.join(email_design.draft_dir(aid), "design.json"))
    # Her note is shown BESIDE the email on his card (GET /api/approvals/{id}/email), never put
    # into approvals.content: line 1 of content is the subject, and dispatch fact-checks all of it.
    if note:
        open(os.path.join(email_design.draft_dir(aid), "vivian_note.txt"), "w", encoding="utf-8").write(note)
    _log(f"#{aid}: Vivian {'designed it' if designed else 'did NOT produce a design'} "
         f"(tools {data.get('tool_calls') or 'none'})")
    return designed


async def draft_now(kind: str | None = None) -> dict:
    """Manual trigger (a test, or Barry saying 'do this week's now')."""
    slots = upcoming_slots()
    send_at, idx = slots[0] if slots else (
        datetime.datetime.now() + datetime.timedelta(hours=1), 0)
    return await draft(kind or kind_for(send_at, idx), send_at)


async def tick() -> None:
    """One look: is a slot within its drafting window, on the clock, idle, and
    not yet drafted? Then draft it. One per tick, so two never race the GPU."""
    if not clock.is_work_hours():
        return
    if ideation._active_chat_count > 0 or ideation._video_building():
        return
    st = _state()
    now = datetime.datetime.now()
    for send_at, idx in upcoming_slots(now):
        key = _slot_key(send_at)
        if st.get(key):
            continue
        if send_at - now > datetime.timedelta(hours=DRAFT_LEAD_HOURS):
            continue
        kind = kind_for(send_at, idx)
        st[key] = {"kind": kind, "started": now.isoformat(timespec="seconds")}
        _save(st)                      # mark first so a crash cannot double-draft
        res = await draft(kind, send_at)
        st[key].update({"done": now.isoformat(timespec="seconds"), **{
            k: v for k, v in res.items() if k in ("ok", "approval_id", "why")}})
        _save(st)
        return


async def run_cadence_loop() -> None:
    await asyncio.sleep(STARTUP_DELAY_SECONDS)
    while True:
        try:
            await tick()
        except Exception as e:  # noqa: BLE001 -- a loop must never die
            _log(f"loop error: {type(e).__name__}: {e}")
        await asyncio.sleep(CHECK_EVERY_SECONDS)
