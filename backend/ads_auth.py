"""MICROSOFT ADVERTISING OAUTH -- one sign-in, then it runs itself.

Barry, 2026-08-30: "i dont want to drop a file. it should be automatic and
totally live."

THE SHAPE, and why it is this and not what it looks like it should be:

The Microsoft Advertising API has **no app-only / client-credentials path**.
Ad accounts are bound to a USER identity, so there is no "application
permission" to grant and a client secret buys nothing. A second Claude session
started creating one on 2026-08-30 -- correct instinct for Microsoft Graph,
dead end here. Do not add a secret.

What makes it unattended is the REFRESH TOKEN. Barry signs in once, in a real
browser, and we keep the refresh token. Microsoft Advertising refresh tokens
last ~90 days AND roll forward every time they are used, so a feed that polls
twice a day never needs him again. If it ever does expire, `authorize()` is one
command and he is back.

DESIGN NOTES:
- **PKCE, no secret.** The app is registered as a public client
  (mobile & desktop, redirect http://localhost:8421), which is the correct
  registration for this API. PKCE is what makes that safe without a secret.
- **The redirect lands on localhost.** The auth code never leaves his machine;
  a tiny one-shot HTTP server catches it and shuts down immediately.
- **No new dependencies.** httpx is already in the venv; everything else is
  stdlib. This project is offline-first and does not need a SOAP SDK to
  authenticate.
- **Secrets stay in .env, written by him.** This module READS
  MSADS_DEVELOPER_TOKEN / MSADS_CLIENT_ID / MSADS_REFRESH_TOKEN and, on a
  successful sign-in, writes ONLY the refresh token back -- in place, without
  touching or reordering any other line in the file.
- ⚠️ **This path is a real outbound call**, unlike the CSV feed. Offline Mode
  is checked by the caller (ads_feed), not silently bypassed here.
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import os
import re
import secrets
import threading
import urllib.parse
import webbrowser

import httpx

# The consumer+organizations endpoint. His ads sit under a PERSONAL Microsoft
# account (bdubbgrows@gmail.com), which is exactly why the app registration is
# "Any Entra ID Tenant + Personal Microsoft accounts" -- a single-tenant app
# against the auto-created .onmicrosoft.com directory can lock out the very
# identity that owns the ads.
AUTHORITY = "https://login.microsoftonline.com/common/oauth2/v2.0"
REDIRECT_URI = "http://localhost:8421"
# msads.manage is the only scope the Advertising API takes; offline_access is
# what actually returns a refresh token.
SCOPES = "https://ads.microsoft.com/msads.manage offline_access"

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(_ROOT, ".env")


def _env(name: str) -> str:
    v = os.environ.get(name)
    if v:
        return v.strip()
    try:
        with open(ENV_PATH, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith(f"{name}=") and not line.startswith("#"):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def _write_env(name: str, value: str) -> None:
    """Set one key in .env, leaving every other line byte-identical.

    Deliberately surgical: his .env is hand-maintained and holds live store
    credentials. A rewrite-the-whole-file approach would eventually reorder or
    drop something of his.
    """
    lines, found = [], False
    try:
        with open(ENV_PATH, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        pass
    for i, line in enumerate(lines):
        if re.match(rf"\s*{re.escape(name)}\s*=", line) and not line.strip().startswith("#"):
            lines[i] = f"{name}={value}"
            found = True
            break
    if not found:
        lines.append(f"{name}={value}")
    with open(ENV_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def status() -> dict:
    """What is configured, without ever revealing a value."""
    return {
        "developer_token": bool(_env("MSADS_DEVELOPER_TOKEN")),
        "client_id": bool(_env("MSADS_CLIENT_ID")),
        "refresh_token": bool(_env("MSADS_REFRESH_TOKEN")),
    }


class _CatchCode(http.server.BaseHTTPRequestHandler):
    code = None
    error = None

    def do_GET(self):  # noqa: N802
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _CatchCode.code = (q.get("code") or [None])[0]
        _CatchCode.error = (q.get("error_description") or q.get("error") or [None])[0]
        body = ("<h2>Signed in.</h2><p>You can close this tab and go back to "
                "Claude.</p>" if _CatchCode.code else
                f"<h2>Sign-in failed</h2><p>{_CatchCode.error}</p>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *a):  # keep the console clean
        pass


def authorize(timeout_s: int = 300) -> dict:
    """ONE-TIME: open the browser, let Barry sign in, keep the refresh token.

    Everything after this is unattended.
    """
    client_id = _env("MSADS_CLIENT_ID")
    if not client_id:
        return {"ok": False, "why": "MSADS_CLIENT_ID is not set in .env"}

    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    state = secrets.token_urlsafe(16)

    url = f"{AUTHORITY}/authorize?" + urllib.parse.urlencode({
        "client_id": client_id, "response_type": "code",
        "redirect_uri": REDIRECT_URI, "scope": SCOPES,
        "state": state, "code_challenge": challenge,
        "code_challenge_method": "S256", "prompt": "select_account",
    })

    _CatchCode.code = _CatchCode.error = None
    server = http.server.HTTPServer(("127.0.0.1", 8421), _CatchCode)
    server.timeout = timeout_s
    t = threading.Thread(target=server.handle_request, daemon=True)
    t.start()
    print("\nA browser window is opening. Sign in with the Microsoft account "
          "that OWNS THE ADS (bdubbgrows@gmail.com).\nIf it does not open, "
          f"paste this into your browser:\n\n{url}\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    t.join(timeout_s)
    server.server_close()

    if _CatchCode.error:
        return {"ok": False, "why": _CatchCode.error}
    if not _CatchCode.code:
        return {"ok": False, "why": "timed out waiting for sign-in"}

    r = httpx.post(f"{AUTHORITY}/token", timeout=30, data={
        "client_id": client_id, "grant_type": "authorization_code",
        "code": _CatchCode.code, "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier, "scope": SCOPES,
    })
    if r.status_code != 200:
        return {"ok": False, "why": f"token exchange failed: {r.text[:300]}"}
    tok = r.json()
    refresh = tok.get("refresh_token")
    if not refresh:
        return {"ok": False, "why": "no refresh_token returned -- is "
                                    "offline_access in the scopes?"}
    _write_env("MSADS_REFRESH_TOKEN", refresh)
    return {"ok": True, "expires_in": tok.get("expires_in"),
            "note": "refresh token saved to .env; no further sign-ins needed"}


def access_token() -> tuple[str | None, str]:
    """A fresh access token from the stored refresh token.

    Microsoft rotates the refresh token on most exchanges, so the new one is
    written straight back -- miss that and the feed silently dies in 90 days.
    """
    client_id, refresh = _env("MSADS_CLIENT_ID"), _env("MSADS_REFRESH_TOKEN")
    if not client_id:
        return None, "MSADS_CLIENT_ID is not set in .env"
    if not refresh:
        return None, "not signed in yet -- run ads_auth.authorize() once"
    r = httpx.post(f"{AUTHORITY}/token", timeout=30, data={
        "client_id": client_id, "grant_type": "refresh_token",
        "refresh_token": refresh, "scope": SCOPES,
    })
    if r.status_code != 200:
        return None, f"refresh failed ({r.status_code}): {r.text[:300]}"
    tok = r.json()
    if tok.get("refresh_token") and tok["refresh_token"] != refresh:
        _write_env("MSADS_REFRESH_TOKEN", tok["refresh_token"])
    return tok.get("access_token"), ""


if __name__ == "__main__":
    print("config:", status())
    print(authorize())
