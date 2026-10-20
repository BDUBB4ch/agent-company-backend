"""DEREK'S EYES ON OMNISEND -- read-only, summarised, never a raw dump.

Barry, 2026-09-01: "i need someone to run the omnisend. i need you to do it and
take Derek with you to teach him everything. I need him to be able to do it."
Asked how far Derek goes on his own, he chose: **build and queue for approval,
never send** and **read everything, propose changes**. This module is the
"read everything" half.

WHY A SEPARATE MODULE FROM `omnisend_client.py`, which already talks to the
same API: exactly the reason `store.py` is separate from anything that can
write to WooCommerce. `omnisend_client` exists to SEND -- it is the tail end of
the approval pipeline and dispatch.py owns it. This file is handed to an agent
that reasons on its own, so the safety property has to be STRUCTURAL rather
than remembered: **there is no write verb in here at all.** `_get` is the only
request path in the file. An agent holding these tools cannot email a customer,
edit a form, change a contact or touch an automation, because the capability
does not exist in the code it can reach -- not because it was told not to.

SUMMARISED, NOT DUMPED. A raw `get_contacts` on this account returns ~34 full
records and roughly 40,000 characters, which would blow a chunk of Derek's
context to answer "how big is the list". Every function here returns the
DECISION-SHAPED answer -- counts, flags, the specific records that are wrong --
and says how to see more. Same discipline as `store.sales_summary`, and the
same reason: a database pretending to be a document is the thing this office
keeps getting wrong.

OFFLINE MODE STRIPS THESE (wired in main.py, like the store tools). They are
outbound calls to a third party; a privacy switch that left them attached would
be a hole that talks.

Degrades, never explodes: with no API key every function returns a plain
sentence telling Barry what to add, exactly like store.py did while it was
unconfigured. Nothing here can raise into a chat.
"""

from __future__ import annotations

import httpx

import omnisend_client

TIMEOUT = 30.0

# ⚠️ OMNISEND HAS TWO API SURFACES AND THEY ARE NOT INTERCHANGEABLE (found the
# hard way 2026-09-01 -- see the longer note in omnisend_client.py, which owns
# the roots and the version constant so they cannot drift between files).
# The reads below stay on the LEGACY v5 root on purpose: its contact and
# automation payloads are the ones this parsing was verified against, and the
# current `/api` surface returns a DIFFERENT automation shape (`isEnabled`,
# `blocks`, no `messages`). Forms do not exist on v5 at all, so they -- and
# every write in omnisend_client -- go through the current surface + header.
API_ROOT = omnisend_client.LEGACY_ROOT
FORMS_ROOT = omnisend_client.API_ROOT
FORMS_VERSION = omnisend_client.API_VERSION

_NO_KEY = ("Omnisend isn't connected yet -- there's no API key set, so I can't "
           "see the account. Barry needs to add OMNISEND_API_KEY to the .env "
           "file (Omnisend -> Store settings -> Integrations & API -> API keys). "
           "Tell him that rather than guessing at numbers.")


def is_configured() -> bool:
    return omnisend_client.is_configured()


def _get(path: str, params: dict | None = None, forms_api: bool = False):
    """The ONLY request path in this module, and it is a GET. See the module
    docstring: this is the structural half of the read-only guarantee."""
    key = omnisend_client._key()
    if not key:
        return None
    root = FORMS_ROOT if forms_api else API_ROOT
    headers = {"X-API-KEY": key}
    if forms_api:
        headers["Omnisend-Version"] = FORMS_VERSION
    try:
        r = httpx.get(f"{root}{path}", params=params or {}, timeout=TIMEOUT,
                      headers=headers)
    except httpx.HTTPError as e:
        return {"_error": f"Could not reach Omnisend: {e}"}
    if r.status_code >= 400:
        return {"_error": f"Omnisend {r.status_code}: {r.text[:300]}"}
    try:
        return r.json() if r.content else {}
    except ValueError:
        return {"_error": "Omnisend returned something that wasn't JSON."}


def _err(data) -> str | None:
    return data.get("_error") if isinstance(data, dict) and "_error" in data else None


def list_status() -> str:
    """THE ONE CALL THAT ANSWERS 'can we send yet'.

    Deliberately leads with the blockers rather than the headline number,
    because on this account the headline number is misleading: every contact
    was bulk-subscribed by Barry in one action on 2026-08-12, which is a
    machine timestamp and not evidence anybody asked to hear from him. An
    agent that reads "33 subscribed" and proposes a blast has read it wrong.
    """
    if not is_configured():
        return _NO_KEY
    data = _get("/contacts", {"limit": 250})
    if (e := _err(data)):
        return e
    contacts = (data or {}).get("contacts") or []
    if not contacts:
        return "No contacts in Omnisend at all."

    subbed = bots = no_name = 0
    bad_phone = []
    bot_addrs = []
    for c in contacts:
        tags = [str(t).lower() for t in (c.get("tags") or [])]
        is_sub = False
        for ident in c.get("identifiers") or []:
            ch = (ident.get("channels") or {}).get("email") or {}
            if ch.get("status") == "subscribed":
                is_sub = True
            sms = (ident.get("channels") or {}).get("sms") or {}
            if sms.get("status") == "subscribed":
                num = str(ident.get("id") or "")
                if not num.startswith("+"):     # not E.164 -- unusable and junk
                    bad_phone.append(f"{c.get('email')} ({num})")
        if is_sub:
            subbed += 1
        if any("spam" in t for t in tags):
            bots += 1
            bot_addrs.append(c.get("email"))
        if not (c.get("firstName") or "").strip():
            no_name += 1

    lines = [
        f"OMNISEND LIST -- {len(contacts)} contacts, {subbed} subscribed to email.",
        "",
        "HOW THEY GOT THERE (this is the part that matters): they were bulk-",
        "subscribed manually in one action, not collected by the signup form.",
        "That is not consent evidence. Emailing existing customers is defensible",
        "under CAN-SPAM; treating this as an opted-in list is not.",
        "",
        "BEFORE A FIRST CAMPAIGN:",
        f"  - {bots} contact(s) tagged suspected-spam and still subscribed"
        + (f": {', '.join(str(a) for a in bot_addrs if a)}" if bot_addrs else ""),
        f"  - {no_name} contact(s) with no first name (bot signature on this store)",
        "  - the sending domain is not authenticated -- mail goes out from the",
        "    shared soundest1.com subdomain, which throttles a first send",
    ]
    if bad_phone:
        lines.append(f"  - SMS still subscribed on an unusable number: "
                     f"{', '.join(bad_phone)} -- UI fix only, the API rejects it")
    lines.append("")
    lines.append("Start with 20-30 known-good customers, never the whole list.")
    return "\n".join(lines)


def list_campaigns(limit: int = 20) -> str:
    """Every campaign and its state. Zero is a real answer and says so."""
    if not is_configured():
        return _NO_KEY
    data = _get("/campaigns", {"limit": max(1, min(int(limit or 20), 100))})
    if (e := _err(data)):
        return e
    camps = (data or {}).get("campaigns") or []
    if not camps:
        return ("No campaigns exist in Omnisend -- not a draft, not a sent one. "
                "Nothing has ever gone out from this account.")
    out = [f"{len(camps)} campaign(s):"]
    for c in camps[:limit]:
        out.append(f"  - {c.get('name')} [{c.get('status')}] "
                   f"subject: {c.get('subject') or '(none)'} "
                   f"id: {c.get('campaignID') or c.get('id')}")
    return "\n".join(out)


def list_forms() -> str:
    """The signup popup and anything like it -- what customers actually see."""
    if not is_configured():
        return _NO_KEY
    data = _get("/forms", forms_api=True)
    if (e := _err(data)):
        return e
    forms = (data or {}).get("forms") or []
    if not forms:
        return "No signup forms exist -- nothing is collecting email addresses."
    out = [f"{len(forms)} form(s) -- this is what actually collects addresses:"]
    for f in forms:
        live = str(f.get("status", "")).lower() == "enabled"
        out.append(f"  - {f.get('name')} [{'LIVE' if live else f.get('status')}] "
                   f"type: {f.get('displayType') or f.get('type') or '?'} "
                   f"id: {f.get('id') or f.get('formID')}")
    return "\n".join(out)


def list_automations() -> str:
    """The flows that fire at customers on their own -- the highest-risk
    objects in the account, which is exactly why Derek can only READ them."""
    if not is_configured():
        return _NO_KEY
    data = _get("/automations")
    if (e := _err(data)):
        return e
    autos = (data or {}).get("automations") or []
    if not autos:
        return "No automations exist."
    out = [f"{len(autos)} automation(s) -- these send WITHOUT anyone pressing "
           f"send, so a change here is live the moment it is made:"]
    for a in autos:
        # ⚠️ THE FIELD IS `status: "enabled"`, NOT a boolean `enabled`.
        # The first version of this read a.get("enabled"), got None for every
        # row, and reported ALL SIX FLOWS AS OFF -- which would have had Derek
        # telling Barry his abandoned-cart emails had stopped running. Caught
        # only by dumping the raw payload instead of trusting the guess. Third
        # time this codebase has been bitten by an assumed field name (traces
        # `final_content`, graph `type`/`s`/`t`). READ THE PAYLOAD.
        live = str(a.get("status", "")).lower() == "enabled"
        msgs = a.get("messages") or []
        out.append(f"  - {a.get('name')} [{'ENABLED' if live else a.get('status') or 'off'}]"
                   f" trigger: {a.get('trigger') or '?'}"
                   f" ({len(msgs)} message{'s' if len(msgs) != 1 else ''})"
                   f" id: {a.get('id') or a.get('automationID')}")
    return "\n".join(out)


def list_templates() -> str:
    """Every saved email template -- what a campaign can be built FROM.

    Lives on the current `/api` surface (v5 has no templates endpoint at all,
    which is how the send path sat broken for two weeks). A campaign cannot
    exist without a templateID, so this list is the starting point for any
    proposal that reuses a design instead of importing fresh HTML.
    """
    if not is_configured():
        return _NO_KEY
    data = _get("/email-templates", {"limit": 50}, forms_api=True)
    if (e := _err(data)):
        return e
    temps = (data or {}).get("templates") or []
    if not temps:
        return "No saved email templates. Every campaign so far was imported from HTML."
    out = [f"{len(temps)} saved template(s) -- a campaign is created FROM one of "
           f"these (templateID) or from freshly imported HTML:"]
    for t in temps:
        out.append(f"  - {t.get('name')} | created {str(t.get('createdAt', ''))[:10]} "
                   f"| id: {t.get('id')}")
    out.append("Note: templates named 'Agent draft #N' are imports dispatch made for "
               "a queued email; the older named ones were built by hand. A template "
               "for a retired offer (e.g. a 20% promo) must not be reused as-is.")
    return "\n".join(out)


