from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .state import MonitorState

ROOT = Path(__file__).resolve().parent
DASHBOARD = ROOT / "dashboard"


class DashboardHandler(BaseHTTPRequestHandler):
    state: MonitorState

    def do_GET(self):
        if self.path.startswith("/api/state"):
            self._json_response(self.state.snapshot())
            return
        if self.path in ("/", "/index.html"):
            self._html_response()
            return
        self.send_error(404)

    def _json_response(self, data: Any):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html_response(self):
        path = DASHBOARD / "index.html"
        if not path.exists():
            self.send_error(404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


def start_dashboard(state: MonitorState, port: int = 8765) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (DashboardHandler,), {"state": state})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    server.daemon_threads = True
    return server
