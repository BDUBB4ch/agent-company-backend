"""The dashboard server for 127.0.0.1:8765 (2026-10-17, Barry: "i thought this was local. how is firefox caching
anything?"). Python's http.server, plus Cache-Control: no-store on every response so a normal reload always shows the
live decks (the plain server sends no cache headers and Firefox kept September's files-panel.js for a month).
Binds 127.0.0.1 ONLY -- not an option, not a flag (Barry: "i dont want nobody being able to just go onto my office").
    python scripts/dashboard_server.py [port] [directory]
Launched by scripts/stack_watchdog.ps1 and Desktop/Launchers/Start Everything.bat."""
import http.server
import os
import sys


class NoStoreHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, format, *args):  # noqa: A002 -- quiet like the old server with -WindowStyle Hidden
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    if len(sys.argv) > 2:
        os.chdir(sys.argv[2])
    http.server.ThreadingHTTPServer(("127.0.0.1", port), NoStoreHandler).serve_forever()
