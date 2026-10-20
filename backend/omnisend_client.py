"""Omnisend API client -- the send half of the approval queue.

Deliberately small. Five calls, no model in the loop, no cleverness:

    import_template  -> POST /api/email-templates/import
    create_campaign  -> POST /api/campaigns          (always lands as a draft)
    send_test        -> POST /api/campaigns/{id}/test-email
    send_campaign    -> POST /api/campaigns/{id}/send
    cancel_campaign  -> POST /api/campaigns/{id}/cancel

WHY A TEMPLATE FIRST: a campaign cannot be created from raw text -- Omnisend
rejects creation without a templateID, even for a draft. So approved content is
imported as a template, then attached. Both steps carry the SAME bytes; nothing
is re-generated between Barry's approval and the send. That is his hard rule:
"it has to be the exact one I approved."

senderEmail is deliberately NEVER sent. Omitting it makes Omnisend use whatever
sender the brand has configured (currently the shared domain). The API cannot
report which addresses are valid, so guessing one gets the request rejected --
and inventing a From address for someone's business is not a thing to guess at.

Credentials come from the environment only, never a function argument, and are
never logged. Same pattern as store.py.
"""
import os

import httpx
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

# ⚠️ TWO API SURFACES, AND THE SEND PATH WAS ON THE DEAD ONE (found 2026-09-01,
# the first time a real key was in .env). `/v5` still answers contacts,
# campaigns (GET) and automations -- but it has NO email-templates endpoints at
# all (404) and rejects campaign creation (405). So import_template, the very
# first call dispatch makes, could never have succeeded: the send pipeline was
# wired 2026-08-15 and "verified" only in dry-run, which touches no network.
#
# The current surface is `/api` and it REQUIRES an `Omnisend-Version` date
# header (400 naming the header if omitted). Versions are retired on a rolling
# basis -- 2026-01-01 and earlier answer 410 "Version retired"; 2026-04-01
# onward work. Pinned to the oldest still-supported date (most stable). When it
# retires the failure is loud and self-describing, and _post surfaces the API's
# own text. Fix = bump API_VERSION.
API_ROOT = "https://api.omnisend.com/api"
API_VERSION = "2026-04-01"
LEGACY_ROOT = "https://api.omnisend.com/v5"    # read-only fallback, no header
TIMEOUT = 30.0


def headers() -> dict:
    """The one place the auth + version headers are assembled. Never logged."""
    return {"X-API-KEY": _key() or "", "Omnisend-Version": API_VERSION,
            "Content-Type": "application/json"}


class OmnisendError(RuntimeError):
    """Raised with the API's own message so the dashboard can show it verbatim."""


def _key() -> str | None:
    return os.getenv("OMNISEND_API_KEY") or None


def is_configured() -> bool:
    return bool(_key())


def status() -> str:
    """Human-readable readiness line, safe to show anywhere -- never the key."""
    return ("Omnisend: API key set." if is_configured()
            else "Omnisend: no API key -- add OMNISEND_API_KEY to .env "
                 "(Omnisend -> Store settings -> Integrations & API -> API keys).")


def _post(path: str, payload: dict | None = None) -> dict:
    key = _key()
    if not key:
        raise OmnisendError("No OMNISEND_API_KEY set -- nothing was sent.")
    try:
        r = httpx.post(f"{API_ROOT}{path}", json=payload or {}, timeout=TIMEOUT,
                       headers=headers())
    except httpx.HTTPError as e:
        raise OmnisendError(f"Could not reach Omnisend: {e}") from e
    if r.status_code >= 400:
        # Surface Omnisend's own wording -- "sender-email-not-available" and
        # friends are actionable, our paraphrase of them would not be.
        raise OmnisendError(f"Omnisend {r.status_code}: {r.text[:400]}")
    return r.json() if r.content else {}


def import_template(name: str, html: str) -> str:
    """Upload approved HTML as a template. Returns its templateID."""
    data = _post("/email-templates/import", {"name": name, "html": html})
    tid = data.get("id") or data.get("templateID")
    if not tid:
        raise OmnisendError(f"Template import returned no id: {str(data)[:200]}")
    return tid


def create_campaign(name: str, subject: str, sender_name: str, template_id: str,
                    segment_ids: list[str] | None = None,
                    preheader: str | None = None,
                    scheduled_at: str | None = None) -> str:
    """Create the campaign as a DRAFT. Returns the campaign id.

    An empty/omitted segment list means every subscriber -- that is Omnisend's
    rule, not ours, and it is why the caller must pass this explicitly rather
    than let it default silently.

    scheduled_at (RFC 3339, must be in the future, within a year) makes the
    send step SCHEDULE instead of fire: Omnisend holds it and sends at that
    moment on its own servers -- which is how a Saturday-morning email goes
    out while Barry's PC is off (the cadence, 2026-09-01).
    """
    email: dict = {"subject": subject, "senderName": sender_name,
                   "templateID": template_id}
    if preheader:
        email["preheader"] = preheader
    payload: dict = {"name": name, "type": "regular", "channel": "email",
                     "language": "en_US", "content": {"email": email}}
    if segment_ids:
        payload["audience"] = {"includedSegmentIDs": segment_ids}
    if scheduled_at:
        payload["sendingSettings"] = {"strategy": "scheduled",
                                      "scheduledAt": scheduled_at}
    data = _post("/campaigns", payload)
    cid = data.get("id")
    if not cid:
        raise OmnisendError(f"Campaign create returned no id: {str(data)[:200]}")
    return cid


def send_test(campaign_id: str, to_email: str) -> dict:
    # Field is `recipients` (1-5 addresses), NOT `email` -- the first live test
    # send 400'd on this, 2026-09-01. Confirmed against the API schema.
    return _post(f"/campaigns/{campaign_id}/test-email", {"recipients": [to_email]})


def send_campaign(campaign_id: str) -> dict:
    """The irreversible one. Everything above this line is undoable."""
    return _post(f"/campaigns/{campaign_id}/send")


def cancel_campaign(campaign_id: str) -> dict:
    """Abort a scheduled/sending campaign. The reason approve-means-send is
    survivable: there is a stop button."""
    return _post(f"/campaigns/{campaign_id}/cancel")
