#!/usr/bin/env python3
"""Isolated real-Nginx loopback-only V2 guard smoke test (NO deployment).

- Refuses to start if sha-pinned V2 route and sandbox preflight fail.
- Starts nginx only INSIDE a new network namespace with a single lo device.
- Uses temporary self-signed cert and synthetic loopback MCP HTTP server.
- Never connects to host PRP 11000 or MCP 18082; no public route exists.
- Does NOT prove public IPv6, production TLS, authenticated MCP, or OAuth.
"""
import http.client
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import audit_v2_route_semantics as semantics
import isolated_v2_nginx_syntax as sandbox
import preflight_v2_netns as netns

HOST = "prp-test.micor.top"
STATUS_READY = "ISOLATED_V2_LOOPBACK_HTTP_ACCEPTANCE_PASSED"
STATUS_EDGE = "ISOLATED_V2_EDGE_HOST_AND_PATH_MATRIX_PASSED"

# Literal, reviewed test cases only. No arbitrary caller input, no DNS queries.
EDGE_WRONG_HOST = (
    ("edge_wrong_host_mcp", "/api/mcp"),
    ("edge_wrong_host_link", "/api/mcp/link"),
    ("edge_wrong_host_discovery", "/.well-known/oauth-protected-resource/api/mcp"),
    ("edge_wrong_host_auth_metadata", "/.well-known/oauth-authorization-server"),
    ("edge_wrong_host_slash", "/api/mcp/"),
    ("edge_wrong_host_encoded", "/api/%6dcp"),
    ("edge_wrong_host_wrong_prefix", "/prp/api/mcp"),
)
EDGE_CANONICAL_ALIASES = (
    ("edge_alias_slash", "/api/mcp/"),
    ("edge_alias_extra", "/api/mcp/extra"),
    ("edge_alias_wrong_prefix", "/prp/api/mcp"),
    ("edge_alias_double_slash", "//api/mcp"),
    ("edge_alias_pct_letter", "/api/%6dcp"),
    ("edge_alias_pct_slash", "/api/mcp%2F"),
    ("edge_alias_dot_segments", "/api/../api/mcp"),
)

class MockMcpHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def do_POST(self):
        self.handle_request()
    def do_GET(self):
        self.handle_request()
    def handle_request(self):
        if len(self.path) > 256 or self.headers.get("content-length") not in ("0", None):
            self.send_error(400)
            return
        self.server.hits.append((self.command, self.path))
        payload = b'{"synthetic_mcp_upstream":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    def log_message(self, *args):
        pass

def run_checked(argv, timeout, **kwargs):
    return subprocess.run(argv, timeout=timeout, capture_output=True, text=True, **kwargs)

def require_own_namespace(parent_namespace):
    child_namespace = os.readlink("/proc/self/ns/net")
    if child_namespace == parent_namespace:
        raise ValueError("NETWORK_NAMESPACE_NOT_ISOLATED")
    if os.readlink("/proc/1/ns/net") == child_namespace:
        raise ValueError("PID1_NETWORK_NAMESPACE_NOT_ISOLATED")
    interfaces = [name for _, name in socket.if_nameindex()]
    if interfaces != ["lo"]:
        raise ValueError("NAMESPACE_CONTAINS_NON_LOOPBACK_INTERFACE")
    result = run_checked([shutil.which("ip"), "link", "set", "dev", "lo", "up"], 5)
    if result.returncode:
        raise ValueError("ISOLATED_LOOPBACK_ENABLE_FAILED")
    if [name for _, name in socket.if_nameindex()] != ["lo"]:
        raise ValueError("ISOLATED_INTERFACE_SET_CHANGED")
    for args in (["-4", "route", "show", "default"],
                 ["-6", "route", "show", "default"]):
        reply = run_checked([shutil.which("ip"), *args], 5)
        if reply.returncode or reply.stdout.strip():
            raise ValueError("ISOLATED_NAMESPACE_HAS_EXTERNAL_ROUTE")
    # Verify ::1 is local in this new namespace (not the host interface).
    try:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        try:
            sock.bind(("::1", 0))
        finally:
            sock.close()
    except OSError:
        raise ValueError("NAMESPACE_IPV6_LOOPBACK_NOT_AVAILABLE")

def make_context(certfile, *, verify_name=True, offer_h2=False):
    ctx = ssl.create_default_context(cafile=str(certfile))
    ctx.check_hostname = verify_name
    ctx.set_alpn_protocols(["h2", "http/1.1"] if offer_h2 else ["http/1.1"])
    return ctx

def tls_socket(ip, family, port, sni, certfile, *, verify_name=True, offer_h2=False):
    raw = socket.socket(family, socket.SOCK_STREAM)
    raw.settimeout(3)
    try:
        raw.connect((ip, port))
        ctx = make_context(certfile, verify_name=verify_name, offer_h2=offer_h2)
        return ctx.wrap_socket(raw, server_hostname=sni)
    except Exception:
        raw.close()
        raise

def http_probe(ip, family, path, host, certfile, *, sni=HOST, method="GET",
               verify_name=True, extra_headers=None):
    with tls_socket(ip, family, 443, sni, certfile, verify_name=verify_name) as conn:
        if conn.selected_alpn_protocol() not in ("http/1.1", None):
            raise ValueError("UNEXPECTED_HTTP2_DURING_HTTP11_TEST")
        extras = extra_headers or {}
        if any("\r" in key or "\n" in key or "\r" in value or "\n" in value
               for key, value in extras.items()):
            raise ValueError("UNSAFE_SYNTHETIC_TEST_HEADER")
        additional = "".join(f"{key}: {value}\r\n" for key, value in extras.items())
        raw = (f"{method} {path} HTTP/1.1\r\nHost: {host}\r\n"
               "Connection: close\r\nContent-Length: 0\r\n"
               + additional + "\r\n").encode("ascii")
        conn.sendall(raw)
        response = http.client.HTTPResponse(conn)
        response.begin()
        response.read(4096)
        return response.status, conn.version()

def bound_and_ready(proc):
    end = time.monotonic() + 7
    while time.monotonic() < end:
        if proc.poll() is not None:
            return False
        try:
            with socket.create_connection(("127.0.0.1", 443), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.1)
    return False

def make_nginx_configuration(sources, root, nginx):
    result = subprocess.run(
        [shutil.which("openssl"), "req", "-x509", "-newkey", "rsa:2048",
         "-nodes", "-days", "1", "-keyout", str(root / "key.pem"),
         "-out", str(root / "cert.pem"), "-subj", "/CN=" + HOST,
         "-addext", "subjectAltName=DNS:" + HOST],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    if result.returncode:
        raise ValueError("SYNTHETIC_TLS_CREATION_FAILED")
    counts = sandbox.prepare(sources, root)
    zone, count = sandbox.recover_single_active_rate_limit(root)
    cfg = root / "nginx.conf"
    cfg.write_text(
        "worker_processes 1;\n"
        "pid " + str(root / "nginx.pid") + ";\n"
        "error_log " + str(root / "nginx-error.log") + " warn;\n"
        "events { worker_connections 32; }\n"
        "http {\n  " + zone + "\n"
        "  include " + str(root / "main.conf") + ";\n"
        "  include " + str(root / "test.conf") + ";\n}\n",
        encoding="utf-8")
    syntax = subprocess.run(
        [nginx, "-t", "-p", str(root) + "/", "-c", str(cfg),
         "-e", str(root / "nginx-error.log")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    if syntax.returncode:
        raise ValueError("ISOLATED_NGINX_SYNTAX_RECHECK_FAILED")
    return cfg, counts, count

def child_run(parent_namespace, *, edge_matrix=False):
    os.umask(0o077)
    require_own_namespace(parent_namespace)
    sources = sandbox.inspect_sources()
    route = semantics.inspect(sources)
    test = route["test"]
    if (test["v2_proxy_directives"] != 2 or
            test["v2_behind_exact_locations"] != 2 or
            test["v2_behind_non_exact_locations"] or
            test["broad_prefix_with_proxy"] or
            test["nonloopback_or_variable_upstream_directives"]):
        raise ValueError("CANDIDATE_ROUTE_POLICY_DRIFT")
    nginx = shutil.which("nginx")
    if not nginx:
        raise ValueError("NGINX_MISSING")

    with tempfile.TemporaryDirectory(prefix="v2-netns-http-", dir=sandbox.ROOT) as folder:
        root = Path(folder)
        config, counts, active_files = make_nginx_configuration(sources, root, nginx)
        # No host 18082 reachable: this synthetic upstream belongs solely to
        # the child namespace's lo interface.
        server = ThreadingHTTPServer(("127.0.0.1", 18082), MockMcpHandler)
        server.hits = []
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        proc = None
        checks = {}
        try:
            proc = subprocess.Popen(
                [nginx, "-p", str(root) + "/", "-c", str(config),
                 "-e", str(root / "nginx-error.log"), "-g", "daemon off;"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if not bound_and_ready(proc):
                raise ValueError("ISOLATED_NGINX_LISTENER_NOT_READY")
            def check(label, *, addr="127.0.0.1", family=socket.AF_INET,
                      path="/api/mcp", host=HOST, sni=HOST, method="GET",
                      verify_name=True, expected=(421,), hits=0,
                      extra_headers=None):
                before = len(server.hits)
                code = None
                fail = None
                try:
                    code, _ = http_probe(
                        addr, family, path, host, root / "cert.pem",
                        sni=sni, method=method, verify_name=verify_name,
                        extra_headers=extra_headers)
                except (OSError, ssl.SSLError, TimeoutError,
                        http.client.HTTPException) as exc:
                    fail = type(exc).__name__
                new_hits = len(server.hits) - before
                checks[label] = {
                    "http_method": method,
                    "status_code": code, "synthetic_upstream_hits": new_hits,
                    "expected_http_code": list(expected),
                    "transport_failure_type": fail,
                    "passed": code in expected and new_hits == hits,
                }
            # Positive case: prove the exact MCP location still reaches only
            # our fake 18082, not a real database/application.
            check("exact_mcp_mock", method="POST", expected=(200,), hits=1)
            check("wrong_host_ipv4", host="untrusted.invalid")
            check("wrong_host_forwarded_spoof", host="untrusted.invalid",
                  extra_headers={"X-Forwarded-Host": HOST})
            check("wrong_path_ipv4", path="/prp/api/mcp",
                  expected=(403, 404, 421))
            check("wrong_host_ipv6", addr="::1", family=socket.AF_INET6,
                  host="untrusted.invalid")
            # An incorrect SNI must not reach our synthetic MCP backend.
            check("wrong_sni_correct_host", sni="untrusted.invalid",
                  verify_name=False, expected=(421,))
            if edge_matrix:
                # Exercise candidate Host rules against routes with differing
                # exact, prefix and regex precedence. All must fail 421.
                for label, path in EDGE_WRONG_HOST:
                    check(label, path=path, host="untrusted.invalid",
                          expected=(421,), hits=0)
                # Distinguish URI normalization behavior from bypass claims.
                # If an alias reaches 18082, the edge gate fails for review.
                # GET might be rejected by an exact MCP method guard
                # *after* Nginx has normalized an alias. Compare a real GET
                # to the canonical endpoint; never assume a 405 means safe.
                check("edge_canonical_get_control", path="/api/mcp",
                      method="GET", expected=(405,), hits=0)
                for label, path in EDGE_CANONICAL_ALIASES:
                    check(label, path=path, method="GET",
                          expected=(400, 403, 404, 421), hits=0)
                    # MCP tools use POST; this is the discriminating request.
                    # Any method-alias hit on the synthetic 18082 must remain
                    # REVIEW_REQUIRED. Never rewrite the guard automatically.
                    check(label.replace("edge_alias_", "edge_post_alias_"),
                          path=path, method="POST",
                          expected=(400, 403, 404, 405, 421), hits=0)
            try:
                with tls_socket("127.0.0.1", socket.AF_INET, 443, HOST,
                                root / "cert.pem", offer_h2=True) as h2:
                    negotiated = h2.selected_alpn_protocol()
                if negotiated not in ("http/1.1", "h2", None):
                    raise ValueError("UNKNOWN_ALPN_SELECTED")
                checks["h2_alpn_only"] = {
                    "selected_alpn": negotiated or "none",
                    "http2_frames_exercised": False,
                }
            except (OSError, ssl.SSLError, TimeoutError) as exc:
                checks["h2_alpn_only"] = {
                    "selected_alpn": "handshake_failure",
                    "handshake_failure_type": type(exc).__name__,
                    "http2_frames_exercised": False,
                }
            passed = (all(v["passed"] for k, v in checks.items()
                          if k != "h2_alpn_only") and
                      checks["h2_alpn_only"]["selected_alpn"] != "handshake_failure")
            return {
                "status": ((STATUS_EDGE if edge_matrix else STATUS_READY)
                           if passed else
                           ("ISOLATED_V2_EDGE_HOST_OR_PATH_REVIEW_REQUIRED"
                            if edge_matrix else
                            "ISOLATED_V2_LOOPBACK_HTTP_ACCEPTANCE_FAILED")),
                "checks": checks,
                "edge_matrix_executed": edge_matrix,
                "edge_canonical_aliases_entering_mock_v2": (
                    sum(checks[label]["synthetic_upstream_hits"] > 0
                        for label, _ in EDGE_CANONICAL_ALIASES)
                    if edge_matrix else None),
                "edge_post_aliases_entering_mock_v2": (
                    sum(checks[label.replace("edge_alias_", "edge_post_alias_")]
                        ["synthetic_upstream_hits"] > 0
                        for label, _ in EDGE_CANONICAL_ALIASES)
                    if edge_matrix else None),
                "canonical_get_method_control_status": (
                    checks["edge_canonical_get_control"]["status_code"]
                    if edge_matrix else None),
                "synthetic_backend_total_requests": len(server.hits),
                "network_interfaces": "LO_ONLY",
                "default_routes": 0,
                "nginx_syntax_in_namespace_passed": True,
                "active_nginx_dependency_files_scanned": active_files,
                "transformed": counts,
                "synthetic_certificate_trust_only": True,
                "production_certificate_tested": False,
                "real_mcp_or_prp_backend_accessed": False,
                "public_ipv6_tested": False,
                "chatgpt_oauth_tested": False,
                "host_nginx_installed_or_reloaded": False,
                "release_approved": False,
            }
        finally:
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

def parent_run(*, edge_matrix=False):
    pre = netns.check_host()
    if pre["status"] != "ISOLATED_NETNS_PREFLIGHT_READY":
        return {"status": "ISOLATED_V2_LOOPBACK_PRECHECK_BLOCKED",
                "blocker": pre.get("blocker", "NETNS_PREFLIGHT_FAILED"),
                "release_approved": False}
    namespace = os.readlink("/proc/self/ns/net")
    try:
        result = subprocess.run(
            [shutil.which("unshare"), "--net", "--fork", "--kill-child",
             sys.executable, "-B", str(Path(__file__).resolve()),
             "--isolated-child", namespace] +
            (["edge"] if edge_matrix else []),
            capture_output=True, text=True, timeout=55)
    except subprocess.TimeoutExpired:
        return {"status": "ISOLATED_V2_LOOPBACK_PRECHECK_BLOCKED",
                "blocker": "NETNS_RUNTIME_TIMEOUT",
                "release_approved": False}
    if not result.stdout or len(result.stdout) > 16000:
        return {"status": "ISOLATED_V2_LOOPBACK_PRECHECK_BLOCKED",
                "blocker": "ISOLATED_CHILD_OUTPUT_MISSING_OR_TOO_LARGE",
                "release_approved": False}
    try:
        child = json.loads(result.stdout)
    except (TypeError, ValueError):
        return {"status": "ISOLATED_V2_LOOPBACK_PRECHECK_BLOCKED",
                "blocker": "ISOLATED_CHILD_REPORT_INVALID",
                "release_approved": False}
    expected_status = STATUS_EDGE if edge_matrix else STATUS_READY
    if (result.returncode == 0) != (child.get("status") == expected_status):
        return {"status": "ISOLATED_V2_LOOPBACK_PRECHECK_BLOCKED",
                "blocker": "ISOLATED_CHILD_EXIT_OR_MODE_MISMATCH",
                "release_approved": False}
    return child

if __name__ == "__main__":
    try:
        if sys.argv[1:2] == ["--isolated-child"] and (
                len(sys.argv) == 3 or
                (len(sys.argv) == 4 and sys.argv[3] == "edge")):
            report = child_run(sys.argv[2],
                               edge_matrix=(len(sys.argv) == 4))
        elif len(sys.argv) == 1:
            report = parent_run()
        elif sys.argv[1:] == ["--edge-matrix"]:
            report = parent_run(edge_matrix=True)
        else:
            raise ValueError("INVALID_INVOCATION")
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError,
            TimeoutError, ssl.SSLError, http.client.HTTPException) as exc:
        report = {
            "status": "ISOLATED_V2_LOOPBACK_PRECHECK_BLOCKED",
            "blocker": str(exc) if isinstance(exc, ValueError) else type(exc).__name__,
            "host_nginx_installed_or_reloaded": False,
            "real_mcp_or_prp_backend_accessed": False,
            "release_approved": False,
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] not in (STATUS_READY, STATUS_EDGE):
        sys.exit(2)
