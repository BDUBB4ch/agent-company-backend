"""Private dashboard server (2026-09-07, Barry: "my office should open up on a
super private url").

Plain `python -m http.server` serves the office at the guessable
http://127.0.0.1:8765/index.html -- anything on this machine that probes port
8765 for /index.html finds the whole office. This server changes that:

  * The office lives under a SECRET path segment (the token below). Only
    http://127.0.0.1:8765/<token>/... is served.
  * ANY request that is not under /<token>/ gets a bare 404 -- including "/"
    and "/index.html". A scanner sees an empty, uninteresting server; there is
    no directory listing, so the token never leaks the way a `-m http.server`
    listing would.
  * Bound to 127.0.0.1 ONLY. Never every interface.

The token is read from data/dashboard_token.txt so it can be rotated without
editing this file -- change that one line, restart the dashboard, done. The
launcher and the watchdog both start THIS script instead of http.server, and
both open http://127.0.0.1:8765/<token>/index.html.

This is a privacy layer, not the security layer. The backend (port 8420) is
what actually refuses outsiders; this just makes the front door unadvertised.
"""
import http.server
import os
import socketserver
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DASH_DIR = os.path.join(os.path.dirname(REPO), "AgentDashboard")
TOKEN_FILE = os.path.join(REPO, "data", "dashboard_token.txt")

PORT = int(os.environ.get("DASHBOARD_PORT", "8765"))
HOST = "127.0.0.1"


def _token() -> str:
    with open(TOKEN_FILE, "r", encoding="utf-8") as fh:
        t = fh.read().strip()
    if not t:
        raise SystemExit("dashboard_token.txt is empty -- refusing to serve with no secret path.")
    return t


TOKEN = _token()
PREFIX = "/" + TOKEN


class Handler(http.server.SimpleHTTPRequestHandler):
    # Serve files out of the dashboard directory regardless of CWD.
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=DASH_DIR, **kw)

    def _under_prefix(self) -> bool:
        p = self.path.split("?", 1)[0].split("#", 1)[0]
        return p == PREFIX or p.startswith(PREFIX + "/")

    def _strip(self):
        # Rewrite /<token>/foo -> /foo before the base handler maps it to disk.
        # A bare /<token> becomes /  (the office index).
        p = self.path
        if p == PREFIX:
            self.path = "/"
        elif p.startswith(PREFIX + "/"):
            self.path = p[len(PREFIX):]

    def do_GET(self):
        if not self._under_prefix():
            self.send_error(404)
            return
        self._strip()
        super().do_GET()

    def do_HEAD(self):
        if not self._under_prefix():
            self.send_error(404)
            return
        self._strip()
        super().do_HEAD()

    def do_POST(self):
        # The dashboard talks to the backend on 8420, never here, but refuse
        # cleanly rather than 501 on anything that does POST to this server.
        self.send_error(404)

    def list_directory(self, path):
        # No directory listings, ever -- a listing is how the token would leak.
        self.send_error(404)
        return None

    def log_message(self, *a):
        pass  # quiet; refusals of interest are the backend's job to record


def main():
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.ThreadingTCPServer((HOST, PORT), Handler) as httpd:
            sys.stderr.write(f"dashboard serving {DASH_DIR} at http://{HOST}:{PORT}{PREFIX}/index.html\n")
            httpd.serve_forever()
    except OSError as e:
        # Something already owns the port -- the watchdog's port guard means
        # this is a duplicate launch; exit quietly rather than crash-loop.
        sys.stderr.write(f"dashboard port {PORT} unavailable ({e}); exiting.\n")
        raise SystemExit(0)


if __name__ == "__main__":
    main()
