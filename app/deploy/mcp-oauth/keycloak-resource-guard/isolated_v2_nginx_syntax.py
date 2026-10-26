#!/usr/bin/env python3
"""Offline, fail-closed nginx -t for fixed MCP V2 guard review files.

Private ephemeral working directory; synthetic certificate; no nginx install,
reload, listener, public request, production TLS private-key read, or approval.
"""
import glob
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT = Path("/root/prp-mcp-cimd-stage-b")
REVIEW = ROOT / "review-only-v2-guard-20261026-01"
FILES = {
    "active_main": (Path("/etc/nginx/conf.d/micor.top.conf"),
                    "ba200a57e880dd286789fcb04ffcf7ce76db4f6005e86bdf934fc9682807792b"),
    "active_test": (Path("/etc/nginx/conf.d/prp-mcp-test.conf"),
                    "35bb31322b23efef536c97e12619ceac7087aa4cf2d56c57f3307232f9362397"),
    "review_main": (REVIEW / "micor.top.guard-v2.REVIEW.conf",
                    "da227c0f6be8c9342d8830cbbe2e76372e4083bff51768c490a0e60c6b18828b"),
    "review_test": (REVIEW / "prp-test.guard-v2.REVIEW.conf",
                    "728b4a3290353f90ea692a2e1ae38a1656101e4381ee3bbdbce6c1cb80964421"),
}
DIRECTIVE = re.compile(r"(?m)^(?P<indent>[ \t]*)(?P<name>[a-zA-Z_][\w]*)[ \t]+(?P<args>[^;\n]*);")
BLOCKED = frozenset({
    "load_module", "ssl_session_ticket_key", "ssl_password_file", "ssl_crl",
    "auth_basic_user_file", "js_import", "init_by_lua", "init_by_lua_file",
    "init_worker_by_lua", "perl", "perl_modules", "perl_require",
    "proxy_cache_path", "fastcgi_cache_path", "uwsgi_cache_path", "scgi_cache_path",
    "client_body_temp_path", "proxy_temp_path", "fastcgi_temp_path",
    "uwsgi_temp_path", "scgi_temp_path", "pid", "lock_file", "dav_methods", "alias",
})
CERT = frozenset({"ssl_certificate", "ssl_trusted_certificate",
                  "ssl_client_certificate", "proxy_ssl_certificate",
                  "proxy_ssl_trusted_certificate"})
KEY = frozenset({"ssl_certificate_key", "proxy_ssl_certificate_key"})
MAX_SIZE = 1024 * 1024

def read_regular(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_SIZE:
            raise ValueError("UNSAFE_OR_OVERSIZE_FILE")
        with os.fdopen(os.dup(fd), "rb") as stream:
            data = stream.read(MAX_SIZE + 1)
        if len(data) != info.st_size:
            raise ValueError("SOURCE_CHANGED_DURING_READ")
        return data
    finally:
        os.close(fd)

def inspect_sources():
    sources = {}
    for name, (path, expected_sha) in FILES.items():
        data = read_regular(path)
        if hashlib.sha256(data).hexdigest() != expected_sha:
            raise ValueError("PINNED_SHA256_DRIFT_" + name.upper())
        sources[name] = data
    if (sources["review_test"].count(b"127.0.0.1:18082") != 2
            or b"127.0.0.1:18081" in sources["review_test"]):
        raise ValueError("V2_LOOPBACK_PORT_MISMATCH")
    return sources

def prepare(sources, target):
    counts = {"includes": 0, "tls_replacements": 0, "log_replacements": 0}
    total_bytes = [0]
    visiting = set()
    dh_files = {}

    def rewrite(data):
        total_bytes[0] += len(data)
        if total_bytes[0] > 3 * MAX_SIZE:
            raise ValueError("TOTAL_CONFIG_LIMIT")
        try:
            source = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("INVALID_CONFIG_ENCODING") from exc

        def replace(match):
            name = match.group("name")
            arg = match.group("args").strip()
            indent = match.group("indent")
            if name in BLOCKED or name.startswith(("lua_", "perl_")):
                raise ValueError("UNSUPPORTED_DIRECTIVE_" + name)
            if name in CERT or name in KEY:
                counts["tls_replacements"] += 1
                file = "key.pem" if name in KEY else "cert.pem"
                return indent + name + " " + str(target / file) + ";"
            if name == "ssl_dhparam":
                if not (arg.startswith("/etc/nginx/") or
                        arg.startswith("/etc/letsencrypt/")):
                    raise ValueError("UNREVIEWED_DHPARAM")
                if arg not in dh_files:
                    if len(dh_files) >= 2:
                        raise ValueError("DHPARAM_FILE_LIMIT")
                    data = read_regular(Path(arg))
                    dest = target / ("dhparam-" + str(len(dh_files) + 1) + ".pem")
                    dest.write_bytes(data)
                    dh_files[arg] = dest
                return indent + name + " " + str(dh_files[arg]) + ";"
            if name in ("access_log", "error_log"):
                counts["log_replacements"] += 1
                return indent + ("access_log off;" if name == "access_log"
                                 else "error_log stderr warn;")
            if name == "include":
                if (not arg.startswith("/") or any(x in arg for x in ('"', "'", "$", "\\")) or
                        not arg.startswith(("/etc/nginx/", "/etc/letsencrypt/")) or
                        "/conf.d/" in arg or "/sites-enabled/" in arg):
                    raise ValueError("UNSAFE_INCLUDE")
                paths = sorted(glob.glob(arg))
                if not paths or len(paths) > 12:
                    raise ValueError("INCLUDE_NOT_BOUNDED")
                statements = []
                for path in paths:
                    if path in visiting or counts["includes"] >= 12:
                        raise ValueError("INCLUDE_CYCLE_OR_LIMIT")
                    counts["includes"] += 1
                    visiting.add(path)
                    dest = target / ("include-" + str(counts["includes"]) + ".conf")
                    dest.write_text(rewrite(read_regular(Path(path))), encoding="utf-8")
                    visiting.remove(path)
                    statements.append(indent + "include " + str(dest) + ";")
                return "\n".join(statements)
            if name in ("proxy_pass", "grpc_pass", "uwsgi_pass",
                        "fastcgi_pass", "scgi_pass"):
                if ("$" not in arg and
                        not re.fullmatch(r"https?://(?:127\.0\.0\.1|\[::1\])(?::\d+)?(?:/[^\s]*)?", arg) and
                        not re.fullmatch(r"(?:127\.0\.0\.1|\[::1\]):\d+", arg)):
                    raise ValueError("UNREVIEWED_PROXY_UPSTREAM")
            return match.group(0)

        rewritten = DIRECTIVE.sub(replace, source)
        # Reject even compact inline forms that the conservative line parser
        # did not rewrite; never let nginx -t reach a production key or log.
        for token in re.finditer(r"(?:^|[;{}])[ \t]*([a-zA-Z_][\w]*)[ \t]+([^;{}\n]*);", rewritten, re.M):
            name, arg = token.group(1), token.group(2).strip()
            if name in BLOCKED or name.startswith(("lua_", "perl_")):
                raise ValueError("UNSUPPORTED_OR_INLINE_DIRECTIVE_" + name)
            if name in CERT and arg != str(target / "cert.pem"):
                raise ValueError("UNREWRITTEN_CERT")
            if name in KEY and arg != str(target / "key.pem"):
                raise ValueError("UNREWRITTEN_KEY")
            if name == "include" and not arg.startswith(str(target) + "/"):
                raise ValueError("UNREWRITTEN_INCLUDE")
            if name == "ssl_dhparam" and not arg.startswith(str(target) + "/"):
                raise ValueError("UNREWRITTEN_DHPARAM")
            if name == "access_log" and arg != "off":
                raise ValueError("UNREWRITTEN_ACCESS_LOG")
            if name == "error_log" and arg != "stderr warn":
                raise ValueError("UNREWRITTEN_ERROR_LOG")
            if name in ("proxy_pass", "grpc_pass", "uwsgi_pass",
                        "fastcgi_pass", "scgi_pass"):
                if ("$" not in arg and
                        not re.fullmatch(r"https?://(?:127\.0\.0\.1|\[::1\])(?::\d+)?(?:/[^\s]*)?", arg) and
                        not re.fullmatch(r"(?:127\.0\.0\.1|\[::1\]):\d+", arg)):
                    raise ValueError("UNREWRITTEN_PROXY_UPSTREAM")
        return rewritten

    for name in ("main", "test"):
        (target / (name + ".conf")).write_text(
            rewrite(sources["review_" + name]), encoding="utf-8")
    return counts

def execute():
    os.umask(0o077)
    sources = inspect_sources()
    nginx, openssl = shutil.which("nginx"), shutil.which("openssl")
    if not nginx or not openssl:
        raise ValueError("NGINX_OR_OPENSSL_MISSING")
    with tempfile.TemporaryDirectory(prefix="syntax-only-v2-", dir=ROOT) as folder:
        temp = Path(folder)
        ssl = subprocess.run([
            openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-days", "1", "-keyout", str(temp / "key.pem"),
            "-out", str(temp / "cert.pem"), "-subj", "/CN=localhost",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        if ssl.returncode:
            raise ValueError("SYNTHETIC_TLS_CREATION_FAILED")
        counts = prepare(sources, temp)
        conf = temp / "nginx.conf"
        conf.write_text(
            "worker_processes 1;\n"
            "pid " + str(temp / "nginx.pid") + ";\n"
            "error_log " + str(temp / "nginx-error.log") + " warn;\n"
            "events { worker_connections 16; }\n"
            "http {\n  include " + str(temp / "main.conf") + ";\n"
            "  include " + str(temp / "test.conf") + ";\n}\n", encoding="utf-8")
        run = subprocess.run(
            [nginx, "-t", "-p", str(temp) + "/", "-c", str(conf),
             "-e", str(temp / "nginx-error.log")],
            capture_output=True, text=True, timeout=25)
        if run.returncode:
            stderr = ((run.stderr or "") + "\n" + (run.stdout or "")).lower()
            return {
                "status": "ISOLATED_NGINX_SYNTAX_FAILED",
                "exit_code": run.returncode,
                "diagnostics": {
                    "unknown_directive": "unknown directive" in stderr,
                    "duplicate_definition": "duplicate" in stderr,
                    "missing_dependency": "no such file or directory" in stderr,
                    "missing_context": "not allowed here" in stderr,
                    "unknown_variable": "unknown " in stderr and "variable" in stderr,
                    "upstream_resolution": "host not found in upstream" in stderr,
                }, "transformed": counts,
                "nginx_install_or_reload": False, "release_approved": False,
            }
        return {
            "status": "ISOLATED_NGINX_SYNTAX_PASSED",
            "exit_code": 0, "transformed": counts,
            "synthetic_tls_only": True,
            "network_or_http_acceptance_tested": False,
            "nginx_install_or_reload": False, "release_approved": False,
        }

if __name__ == "__main__":
    try:
        result = execute()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        result = {
            "status": "ISOLATED_NGINX_PRECHECK_BLOCKED",
            "reason": str(exc) if isinstance(exc, ValueError) else type(exc).__name__,
            "nginx_install_or_reload": False, "release_approved": False,
        }
    print(json.dumps(result, sort_keys=True, indent=2))
    if result["status"] != "ISOLATED_NGINX_SYNTAX_PASSED":
        sys.exit(2)
