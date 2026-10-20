"""Dispatch -- what happens when Barry approves something.

Until now the approval queue was a dead end: `decide_approval` flipped a status
column and stopped. 20 items sat approved and none of them ever went anywhere.
This is the other half, on his instruction: "it stays in agent office waiting
for approval and on approval it gets written and sent".

The rules this file exists to enforce, in order of how badly they'd hurt:

1. NEVER RE-RUN A MODEL between approval and send. The approved bytes in
   approvals.content are what goes out, character for character. His words:
   "it has to be the exact one I approved."
2. NEVER SEND TWICE. dispatched_at is the guard. A retry, a double-click, a
   re-approval, a restart mid-flight -- all must be no-ops.
3. OFFLINE MODE MEANS OFFLINE. The privacy switch strips web search and the
   store tools; a dispatch path that ignored it would be a hole that publishes.
4. NEVER FAIL SILENTLY. Every outcome, including the errors, is written back to
   the row so Pending Review can show what actually happened.

Adding a destination = one function + one line in _ADAPTERS. Nothing else here
needs to know what a campaign is.
"""
import datetime
import json
import re

import memory
import omnisend_client
import factcheck

# action_type (agents.EXTERNAL_ACTION_TYPES) -> where it goes. Anything not
# listed here is deliberately undeliverable: it stays approved, undispatched,
# and says so, rather than guessing a destination for someone's business.
_DESTINATIONS = {
    "email": "omnisend",
}

SENDER_NAME = "B DUBB GROWS LLC"

# THE MASTER SWITCH -- OFF, and off is the default everywhere.
#
# Barry, 2026-08-15, after the send path was finished and wired:
#   "I want to just copy and paste the emails that they create, no need right
#    now for them to write them and send yet. may keep it wired but dont let
#    them be able to send yet. Im not that big yet."
#
# So the plumbing stays and the tap is closed. This is checked FIRST in
# dispatch_approved, before the destination lookup, before the API key, before
# anything touches the network -- an agent cannot send while this is false no
# matter what else is configured. Turning it on is deliberately a decision he
# makes, not a side effect of adding an API key:
#
#     memory.set_setting("dispatch_enabled", "true")
#
# It reads live from app_settings, so flipping it needs no restart and no code
# edit. Nothing else in this file needs to change when he's ready.
DISPATCH_ENABLED_KEY = "dispatch_enabled"


def is_sending_enabled() -> bool:
    return memory.get_setting(DISPATCH_ENABLED_KEY, "false") == "true"


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _record(approval_id: int, destination: str, status: str, response: str) -> dict:
    with memory.get_db() as conn:
        conn.execute(
            "UPDATE approvals SET destination = ?, dispatched_at = ?, "
            "dispatch_status = ?, dispatch_response = ? WHERE id = ?",
            (destination, _now() if status == "sent" else None, status,
             response[:2000], approval_id),
        )
    return {"status": status, "destination": destination, "detail": response}


def _first_line(text: str, fallback: str) -> str:
    for line in (text or "").splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:200]
    return fallback


# --- THE WEEKLY CAP -----------------------------------------------------------
# Barry, 2026-09-01: "once i see that he can make good campaigns and emails,
# ill let him go free to do what he wants, but only twice a week max."
# The cap is enforced HERE, at the one place bytes leave the building, counted
# from rows that actually went out -- not from intentions, not from a counter
# an agent could reset. It applies in BOTH phases: while Barry is approving by
# hand and after he flips autonomy on. A test send does not count; it reaches
# only him.
WEEKLY_CAP_KEY = "email_weekly_cap"
WEEKLY_CAP_DEFAULT = 2
DEFAULT_SEGMENT_KEY = "email_default_segment"   # the "Known customers" segment id


def weekly_cap() -> int:
    try:
        return max(0, int(memory.get_setting(WEEKLY_CAP_KEY, str(WEEKLY_CAP_DEFAULT))))
    except (TypeError, ValueError):
        return WEEKLY_CAP_DEFAULT


def sends_this_week() -> int:
    """Real sends (incl. scheduled ones) in the last 7 days."""
    since = (datetime.datetime.now(datetime.UTC)
             - datetime.timedelta(days=7)).isoformat()
    with memory.get_db() as conn:
        r = conn.execute(
            "SELECT COUNT(*) AS n FROM approvals WHERE action_type = 'email' "
            "AND dispatch_status = 'sent' AND dispatched_at >= ?", (since,)).fetchone()
    return int(r["n"] or 0)


def _default_segment() -> list[str] | None:
    sid = (memory.get_setting(DEFAULT_SEGMENT_KEY, "") or "").strip()
    return [sid] if sid else None


def _split_subject_body(content: str) -> tuple[str, str]:
    """Line 1 is the subject; the rest is the body. `SUBJECT:` prefix optional."""
    lines = (content or "").strip().splitlines()
    if not lines:
        return "A note from B DUBB GROWS", ""
    subject = lines[0].strip().lstrip("#").replace("**", "").strip()
    if subject.lower().startswith("subject:"):
        subject = subject[8:].strip()
    subject = subject[:200] or "A note from B DUBB GROWS"
    return subject, "\n".join(lines[1:]).strip()


def _as_html(body: str) -> str:
    """Deterministic formatting, NOT a rewrite.

    The first live test (2026-09-01) showed the gap: agents draft plain text,
    Omnisend imports HTML, and a raw import renders as one unbroken blob. This
    wraps paragraphs in <p> and guarantees the unsubscribe link. It changes no
    word, reorders nothing, and runs no model -- so the approved text is still
    exactly what goes out; it just has paragraph breaks. Content that is
    already HTML passes through untouched apart from the unsubscribe guarantee.
    """
    import html as _h
    text = (body or "").strip()
    if "<html" in text.lower() or "<body" in text.lower():
        out = text
    elif "<p" in text.lower():
        # Seen live 2026-09-01: one <p> around three paragraphs separated by
        # blank lines, which renders as a single block. Blank lines inside a
        # paragraph tag become paragraph breaks. Still no words touched.
        text = re.sub(r"\n\s*\n", "</p><p>", text)
        out = ("<html><body style=\"font-family:Poppins,Arial,sans-serif;"
               "color:#47704C;max-width:600px\">" + text + "</body></html>")
    else:
        paras = [p.strip() for p in text.split("\n\n") if p.strip()]
        out = ("<html><body style=\"font-family:Poppins,Arial,sans-serif;"
               "color:#47704C;max-width:600px\">"
               + "".join("<p>" + _h.escape(p).replace("\n", "<br>") + "</p>"
                         for p in paras)
               + "</body></html>")
    if "[[unsubscribe_link]]" not in out:
        # 2026-09-26: the business mailbox on plain emails too (the law needs a postal address).
        foot = ('<p style="font-size:12px;color:#888">B DUBB GROWS · 6510-A S Academy Blvd PMB3016, '
                'Colorado Springs, CO 80906-8691, United States<br>'
                '<a href="[[unsubscribe_link]]">Unsubscribe</a></p>')
        out = (out.replace("</body>", foot + "</body>", 1)
               if "</body>" in out else out + foot)
    return out


def _scheduled_at(row: dict) -> str | None:
    """A future send_at becomes an Omnisend scheduled send; past/empty = now."""
    raw = (row.get("send_at") or "").strip()
    if not raw:
        return None
    try:
        when = datetime.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.astimezone()               # stored in Barry's local time
    if when <= datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=2):
        return None
    return when.astimezone(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _send_email(row: dict, *, segment_ids: list[str] | None,
                test_to: str | None) -> str:
    """Approved content -> Omnisend campaign -> sent (or scheduled).

    Two API calls carry the same bytes: a campaign cannot be created from raw
    text, it needs a templateID, so the content is imported as a template first.
    Nothing is regenerated in between.
    """
    subject, body = _split_subject_body(row["content"])
    html = _as_html(body)
    name = f"Agent draft #{row['id']} -- {subject[:60]}"

    # Audience: explicit > the row's own segment > the default segment > (only
    # then) Omnisend's everyone. The default exists so an approve click can
    # never accidentally mean the whole list.
    audience = segment_ids or (
        [row["segment_id"]] if (row.get("segment_id") or "").strip() else None
    ) or _default_segment()
    scheduled = None if test_to else _scheduled_at(row)

    # VIVIAN'S DESIGN (2026-09-26): a designed draft already IS an Omnisend template -- the one
    # whose render Barry saw on his card. Send from THAT template; never re-import the plain text.
    preheader = None
    template_id = (row.get("omnisend_template_id") or "").strip()
    if template_id:
        import email_design
        try:
            preheader = (email_design.load(row["id"])[0].get("preheader") or None)
        except Exception:  # noqa: BLE001 -- no sheet = no preheader, the email is still his
            preheader = None
        # LINKS MUST WORK (Barry, 2026-09-26: "and make sure links work"). Re-checked on the
        # template as it stands NOW, at send time; one broken link = nothing leaves.
        _links = email_design.check_links(email_design.render_html(template_id))
        if _links["broken"]:
            raise omnisend_client.OmnisendError(
                "NOT SENT -- broken link(s) in the email: " + "; ".join(_links["broken"][:5]))
        # PRICES MUST STILL BE TRUE (Barry, 2026-09-26: "yes recheck prices at send too"). A changed
        # price never goes out: the email is rebuilt with today's price and goes BACK to Pending so he
        # sees the new version first. Out of stock = not sent, named.
        try:
            _changed = email_design.price_changes(row["id"])
        except ValueError as e:
            raise omnisend_client.OmnisendError(f"NOT SENT -- {e}")
        if _changed:
            _sheet, _design = email_design.load(row["id"])
            if _design:
                email_design.publish(row["id"], _design, template_id)
            with memory.get_db() as conn:
                conn.execute("UPDATE approvals SET status='pending', decided_at=NULL WHERE id=?", (row["id"],))
            raise omnisend_client.OmnisendError(
                "NOT SENT -- a price changed since you approved it: " + "; ".join(_changed)
                + ". The email was rebuilt with today's price and is back in Pending for your look.")
    else:
        import email_design
        _links = email_design.check_links(html)
        if _links["broken"]:
            raise omnisend_client.OmnisendError(
                "NOT SENT -- broken link(s) in the email: " + "; ".join(_links["broken"][:5]))
        template_id = omnisend_client.import_template(name, html)
    campaign_id = omnisend_client.create_campaign(
        name=name, subject=subject, sender_name=SENDER_NAME,
        template_id=template_id, segment_ids=audience, preheader=preheader, scheduled_at=scheduled)

    if test_to:
        omnisend_client.send_test(campaign_id, test_to)
        return json.dumps({"campaign_id": campaign_id, "template_id": template_id,
                           "sent": False, "test_email_to": test_to})

    omnisend_client.send_campaign(campaign_id)
    return json.dumps({"campaign_id": campaign_id, "template_id": template_id,
                       "sent": True, "scheduled_at": scheduled,
                       "audience": audience})


_ADAPTERS = {"omnisend": _send_email}


def dispatch_approved(approval_id: int, *, segment_ids: list[str] | None = None,
                      test_to: str | None = None, dry_run: bool = False) -> dict:
    """Send one approved item. Safe to call more than once -- it won't resend.

    test_to  -- create the campaign and send only a test to that address. The
                campaign stays a draft, so this is the rehearsal.
    dry_run  -- resolve everything and touch no network at all.
    """
    with memory.get_db() as conn:
        r = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
    if not r:
        return {"status": "skipped", "detail": f"No approval {approval_id}."}
    row = dict(r)

    # First gate, before everything. Nothing an agent does and nothing else in
    # the config can get past this while sending is off.
    if not is_sending_enabled():
        return {"status": "skipped",
                "detail": "Sending is OFF (dispatch_enabled). The draft stays in "
                          "the Out box for Barry to copy out. Nothing was sent."}

    if row.get("status") != "approved":
        return {"status": "skipped",
                "detail": f"Approval {approval_id} is '{row.get('status')}', not approved."}

    if row.get("dispatched_at"):
        return {"status": "skipped",
                "detail": f"Already sent {row['dispatched_at']} -- not sending again."}

    if memory.is_offline_mode():
        return _record(approval_id, "", "skipped",
                       "Offline Mode is on -- nothing leaves this machine.")

    destination = _DESTINATIONS.get(row.get("action_type", ""))
    if not destination:
        return _record(approval_id, "", "skipped",
                       f"No destination wired for action_type "
                       f"'{row.get('action_type')}' -- approved but not sent.")

    if dry_run:
        return {"status": "dry-run", "destination": destination,
                "detail": f"Would send approval {approval_id} ({len(row['content'])} chars) "
                          f"to {destination} as '{_first_line(row['content'], '?')}'."}

    if not omnisend_client.is_configured():
        return _record(approval_id, destination, "failed", omnisend_client.status())

    # ONLY REAL STUFF (Barry, 2026-09-09). Approved bytes still go out verbatim,
    # but not if they are false: #207 told customers Microlife was back in
    # stock while the store said outofstock. Re-checked HERE, at send time,
    # against the live store -- stock can change between draft and send day.
    # A banner from the drafting check is a hard stop too. Tests are exempt
    # (they reach only Barry). Nothing is marked dispatched, so a corrected
    # approval can go later.
    if not test_to and row.get("action_type") == "email":
        if (row.get("content") or "").lstrip().startswith(factcheck.BANNER):
            return _record(approval_id, destination, "blocked",
                           "Not sent: this draft carries the office fact-check banner. "
                           "Fix the claims and approve a corrected draft.")
        chk = factcheck.check_email(row.get("content") or "")
        if not chk["ok"]:
            return _record(approval_id, destination, "blocked",
                           "Not sent -- fact-check failed at send time:\n" + factcheck.report(chk))

    # THE CAP. Tests are exempt (they reach only Barry). A refusal is recorded
    # on the row so the Out box says why, and nothing is marked dispatched, so
    # it can be sent next week without re-approval.
    if not test_to and row.get("action_type") == "email":
        cap = weekly_cap()
        done = sends_this_week()
        if done >= cap:
            return _record(approval_id, destination, "capped",
                           f"Weekly email cap reached ({done}/{cap} in the last 7 "
                           f"days). Not sent. It stays approved; try again next week.")

    # THE CLAIM (2026-09-07). Approval #177 went to Omnisend TWICE on 09-03:
    # two APPROVE clicks landed ~2s apart, the guard above reads dispatched_at
    # BEFORE the network call and _record writes it AFTER, so both requests
    # passed and both created and sent a campaign. FastAPI runs the sync
    # decide() endpoint in a thread pool, so the two really did run side by
    # side. Fix: claim the row in ONE atomic UPDATE before touching the
    # network. Exactly one caller sees rowcount 1; every other concurrent
    # caller sees 0 and stops. A 'sending' claim older than 10 minutes is a
    # crashed run and may be reclaimed. Tests (test_to) don't claim -- they
    # never mark anything sent.
    if not test_to:
        claim_note = f"sending since {_now()}"
        stale = (datetime.datetime.now(datetime.UTC)
                 - datetime.timedelta(minutes=10)).isoformat()
        with memory.get_db() as conn:
            cur = conn.execute(
                "UPDATE approvals SET dispatch_status = 'sending', dispatch_response = ? "
                "WHERE id = ? AND dispatched_at IS NULL AND ("
                "  COALESCE(dispatch_status, '') <> 'sending' "
                "  OR COALESCE(dispatch_response, '') < ?)",
                (claim_note, approval_id, f"sending since {stale}"),
            )
            if cur.rowcount != 1:
                return {"status": "skipped",
                        "detail": "Another send of this approval is already in "
                                  "progress -- not sending it twice."}

    try:
        detail = _ADAPTERS[destination](row, segment_ids=segment_ids, test_to=test_to)
    except Exception as e:  # noqa: BLE001 -- the message is the product here
        return _record(approval_id, destination, "failed", str(e))

    # A test send is a rehearsal, not a send: leave dispatched_at unset so the
    # real send is still possible afterwards.
    return _record(approval_id, destination,
                   "sent" if not test_to else "tested", detail)
