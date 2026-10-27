#!/usr/bin/env python3
"""CI-only actual Nginx acceptance for the uninstalled first-party route plan.

Starts an isolated mock backend (127.0.0.1:18082) and Nginx (127.0.0.1:18084)
only on a disposable GitHub Actions runner. No external host, public
listeners, Keycloak, real data, client tokens, Nginx reload or deployment.
"""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time

from approval_routes_pending import render_readonly_link_routes

HOST = "prp-test.micor.top"
SENTINEL = "PRP_REVIEW_MOCK_ONLY"
TARGET = 18082
EDGE = 18084


class MockHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.answer()

    def do_POST(self):
        self.answer()

    def do_HEAD(self):
        self.answer()

    def answer(self):
        # No response body from any real user. Do not print request URI or
        # OAuth parameters; this is a synthetic mock.
        self.send_response(200)
        self.send_header("X-Review-Mock", SENTINEL)
        self.send_header("X-Review-Method", self.command)
        self.send_header("X-Review-Host", self.headers.get("Host", ""))
        self.send_header("X-Review-Forwarded-Proto",
                         self.headers.get("X-Forwarded-Proto", ""))
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *_args):
        return


def request(path, method="GET", host=HOST, origin=None):
    conn = http.client.HTTPConnection("127.0.0.1", EDGE, timeout=5)
    headers = {"Host": host}
    if origin is not None:
        headers["Origin"] = origin
    try:
        conn.request(method, path, headers=headers)
        response = conn.getresponse()
        status = response.status
        via_mock = response.getheader("X-Review-Mock") == SENTINEL
        forwarded_host = response.getheader("X-Review-Host")
        forwarded_proto = response.getheader("X-Review-Forwarded-Proto")
        response.read()
        return status, via_mock, forwarded_host, forwarded_proto
    finally:
        conn.close()


def assert_result(path, method="GET", allowed=False, host=HOST, origin=None):
    code, via, forwarded_host, forwarded_proto = request(
        path, method, host, origin)
    if allowed:
        if (code != 200 or not via or forwarded_host != HOST
                or forwarded_proto != "https"):
            raise AssertionError("CI_REVIEW_CANONICAL_ROUTE_NOT_FORWARDED")
    else:
        if code == 200 or via:
            raise AssertionError("CI_REVIEW_UNAPPROVED_ROUTE_FORWARDED")
    return True


def main():
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("RUNNER_OS") != "Linux"
            or not os.environ.get("RUNNER_TEMP")):
        raise SystemExit("DISPOSABLE_GITHUB_RUNNER_ONLY")
    if not subprocess.run(["nginx", "-v"], capture_output=True).returncode == 0:
        raise SystemExit("ISOLATED_NGINX_UNAVAILABLE")
    daemon = None
    server = None
    thread = None
    try:
        # No host system Nginx or PRP process is contacted.
        server = ThreadingHTTPServer(("127.0.0.1", TARGET), MockHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        with tempfile.TemporaryDirectory(
                prefix="prp-first-party-nginx-", dir=os.environ["RUNNER_TEMP"]) as tmp:
            folder = Path(tmp)
            snippet = render_readonly_link_routes()
            if (snippet.count("proxy_pass http://127.0.0.1:18082;") != 18
                    or "127.0.0.1:18081" in snippet
                    or "127.0.0.1:18443" in snippet):
                raise AssertionError("CI_REVIEW_UPSTREAM_LINEAGE_DRIFT")
            conf = folder / "nginx.conf"
            conf.write_text(
                "worker_processes 1;\n"
                "pid " + str(folder / "nginx.pid") + ";\n"
                "error_log " + str(folder / "error.log") + " warn;\n"
                "events { worker_connections 64; }\n"
                "http {\n"
                "map $http_origin $prp_stage_origin_ok {\n"
                "  default 0;\n"
                '  "" 1;\n'
                '  "https://prp-test.micor.top" 1;\n'
                "}\n"
                "server {\n"
                "  listen 127.0.0.1:18084;\n"
                "  server_name prp-test.micor.top;\n"
                "  access_log off;\n"
                "  if ($host != prp-test.micor.top) { return 421; }\n"
                + snippet + "\n"
                "  location / { return 404; }\n"
                "}\n"
                "}\n", encoding="utf-8")
            cmd = ["nginx", "-p", str(folder) + "/", "-c", str(conf)]
            syntax = subprocess.run(cmd + ["-t"], capture_output=True,
                                    text=True, timeout=12)
            if syntax.returncode:
                raise AssertionError("CI_REVIEW_NGINX_SYNTAX_FAILED")
            daemon = subprocess.Popen(cmd + ["-g", "daemon off;"],
                                      stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL)
            ready = False
            for _ in range(50):
                if daemon.poll() is not None:
                    raise AssertionError("CI_REVIEW_NGINX_EXITED")
                try:
                    result = request("/prp/login")
                    if result[0] == 200 and result[1]:
                        ready = True
                        break
                except (OSError, http.client.HTTPException):
                    pass
                time.sleep(0.1)
            if not ready:
                raise AssertionError("CI_REVIEW_NGINX_START_FAILED")
            for path, method in (
                ("/prp/login", "GET"),
                ("/prp/me/mcp-clients", "GET"),
                ("/prp/me/mcp-link/callback?code=CI&state=CI", "GET"),
                ("/prp/favicon.svg", "GET"),
                ("/prp/icon.svg", "GET"),
                ("/prp/manifest.webmanifest", "GET"),
                ("/prp/sw.js", "GET"),
                ("/prp/assets/vendor.element-plus.Az91.js", "GET"),
                ("/prp/assets/base-AZ92.css", "GET"),
                ("/api/users/me", "GET"),
                ("/api/mcp/clients", "GET"),
                ("/api/mcp/clients", "POST"),
                ("/api/mcp/identity/oidc/start", "POST"),
                ("/api/mcp/identity/oidc/finish", "POST"),
            ):
                assert_result(path, method, allowed=True)
            print("PASS REVIEW NGINX: 14 canonical HTTP method/path probes forwarded.")

            # Beware nginx normalizes percent-encoded paths before selecting
            # exact locations. The original raw request URI must be checked.
            for path, method in (
                ("/prp/me/mcp-link/%63allback?code=CI&state=CI", "GET"),
                ("/api/mcp/identity/oidc/%73tart", "POST"),
                ("/api/mcp/clients%2frevoke", "POST"),
                ("/api/mcp/%69dentity", "GET"),
                ("/prp/assets/vendor..js", "GET"),
                ("/prp/assets/nested%2findex.js", "GET"),
                ("/api/finance", "GET"),
                ("/api/tasks", "GET"),
                ("/prp/api/mcp", "POST"),
                ("/prp/admin", "GET"),
                ("/prp/login", "POST"),
                ("/api/mcp/identity/oidc/start", "GET"),
            ):
                assert_result(path, method, allowed=False)
            # Nginx limit_except GET also admits HEAD; the mock must
            # implement HEAD so a forwarded request cannot hide as 501.
            for path in ("/prp/login", "/prp/sw.js", "/api/mcp/clients",
                         "/api/users/me"):
                assert_result(path, method="HEAD", allowed=False)
            assert_result("/prp/login", host="unrelated.invalid", allowed=False)
            assert_result("/api/mcp/identity/oidc/start", "POST",
                          origin="https://evil.example", allowed=False)
            print("PASS REVIEW NGINX: 14 denied alias, method, Host, Origin and API probes.")
            print("NO_ACTIVE_NGINX_NO_REAL_KEYCLOAK_NO_EXISTING_V2_OR_DB_CHANGE=YES")
    finally:
        if daemon is not None:
            daemon.terminate()
            try:
                daemon.wait(timeout=8)
            except subprocess.TimeoutExpired:
                daemon.kill()
                daemon.wait(timeout=4)
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=5)


if __name__ == "__main__":
    main()
