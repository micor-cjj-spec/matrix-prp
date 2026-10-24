#!/usr/bin/env python3
"""Loopback-only fake backend for disposable Nginx CI; never runs in PRP production."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass
    def do_GET(self):
        self.handle_echo()
    def do_POST(self):
        self.handle_echo()
    def handle_echo(self):
        response = json.dumps({
            "path": self.path,
            "host": self.headers.get("Host"),
            "forwarded_proto": self.headers.get("X-Forwarded-Proto"),
            "forwarded_host": self.headers.get("X-Forwarded-Host"),
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 11000), Handler).serve_forever()
