#!/usr/bin/env python3
"""Disposable CI-only fake services for testing actual TLS proxy separation."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import json


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        self.echo()

    def do_POST(self):
        self.echo()

    def echo(self):
        data = json.dumps({
            "backend": "stage-prp" if self.server.server_port == 18081 else "stage-keycloak",
            "path": self.path,
            "host": self.headers.get("Host"),
            "forwarded_host": self.headers.get("X-Forwarded-Host"),
            "forwarded_proto": self.headers.get("X-Forwarded-Proto"),
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    servers = [ThreadingHTTPServer(("127.0.0.1", port), Handler)
               for port in (18080, 18081)]
    for service in servers:
        Thread(target=service.serve_forever, daemon=True).start()
    for service in servers:
        service.serve_forever()
