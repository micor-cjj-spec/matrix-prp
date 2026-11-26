"""Synthetic disposable fixture, not an application or a real health endpoint."""
import json
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        status = 200
        body = {"code": "SUCCESS", "data": {"status": "UP", "service": "fixture"}}
        if self.path == "/421":
            status = 421
        elif self.path == "/503":
            status = 503
        elif self.path == "/slow":
            time.sleep(5)
        elif self.path == "/redirect":
            status = 302
        elif self.path == "/recover":
            status = 200 if Path("/tmp/recovered").exists() else 503
        elif self.path == "/degraded":
            body["data"]["status"] = "DEGRADED"
            body["data"]["database"] = "DOWN"
        elif self.path == "/204":
            status = 204
        elif self.path != "/api/health":
            status = 404
        try:
            payload = b"" if status == 204 else json.dumps(body).encode()
            self.send_response(status)
            if status == 302:
                self.send_header("Location", "/api/health")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    http = ThreadingHTTPServer(("0.0.0.0", 8080), Handler)
    tls = ThreadingHTTPServer(("0.0.0.0", 8443), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain("/fixture-tls/leaf.crt", "/fixture-tls/leaf.key")
    tls.socket = context.wrap_socket(tls.socket, server_side=True)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    tls.serve_forever()


if __name__ == "__main__":
    main()
