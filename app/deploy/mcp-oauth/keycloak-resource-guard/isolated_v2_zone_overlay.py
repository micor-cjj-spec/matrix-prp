#!/usr/bin/env python3
"""Isolated syntax acceptance using exactly one proven active rate-limit zone.

Imports two pinned sibling audit helpers. Injects only a strictly validated
limit_req_zone definition into a disposable http context and runs nginx -t.
No live service/config edits, reload, listener or production TLS key reads.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import isolated_v2_nginx_syntax as syntax
import trace_v2_limit_zone as lineage

MAX_ZONE_DIRECTIVE = 300
DEF_RE = re.compile(r"(?m)(?:(?<=^)|(?<=[;{}]))[ \t]*limit_req_zone[ \t]+([^;{}]*);")
NAME_RE = re.compile(r"(?:^|\s)zone=([A-Za-z0-9_.-]+):([0-9]+[kKmMgG]?)(?:\s|$)")
SAFE_ARG_RE = re.compile(
    r"^\$[A-Za-z_][A-Za-z0-9_]*(?:\$[A-Za-z_][A-Za-z0-9_]*)* "
    r"zone=([A-Za-z0-9_.-]+):([0-9]+[kKmM]) "
    r"rate=([1-9][0-9]{0,7}r/[sm])$"
)

def parse_sanitized_definition(raw, target):
    """Return the exact active directive normalized only for whitespace."""
    src = "\n".join(line.split("#", 1)[0]
                    for line in raw.decode("utf-8").splitlines())
    selected = []
    for hit in DEF_RE.finditer(src):
        args = " ".join(hit.group(1).split())
        m = NAME_RE.search(" " + args + " ")
        if not m or m.group(1) != target:
            continue
        if len(args.encode("utf-8")) > MAX_ZONE_DIRECTIVE:
            raise ValueError("LIMIT_ZONE_ARGUMENT_TOO_LONG")
        if not SAFE_ARG_RE.fullmatch(args):
            raise ValueError("LIMIT_ZONE_UNREVIEWED_SYNTAX")
        selected.append("limit_req_zone " + args + ";")
    if len(selected) != 1:
        raise ValueError("LIMIT_ZONE_EXPECTED_ONE_DECLARATION_PER_SOURCE")
    return selected[0]

def find_verified_source():
    sources = syntax.inspect_sources()  # Pinned active vhost and review SHA.
    report = lineage.inspect()          # Complete, bounded live include graph.
    if (report["status"] != "MISSING_ZONE_DEFINED_IN_ACTIVE_INCLUDE_GRAPH"
            or report["candidate_req_zone_missing_count"] != 1
            or report["candidate_conn_zone_missing_count"] != 0
            or report["matching_definition_locations"] != {"NGINX_CONF_D": 1}
            or report["matching_definition_count"] != 1):
        raise ValueError("LIMIT_ZONE_PROVENANCE_NOT_APPROVED")
    defs = {"req": set(), "conn": set()}
    refs = {"req": set(), "conn": set()}
    includes = []
    for name in ("review_main", "review_test"):
        d, r, inc = lineage.parse_config(sources[name])
        for family in defs:
            defs[family].update(d[family])
            refs[family].update(r[family])
        includes.extend(inc)
    # Account for all includes from the *candidate* without copying the
    # active config tree into the test sandbox.
    for p in includes:
        if not p.startswith(("/etc/nginx/", "/etc/letsencrypt/options-ssl-nginx.conf")):
            raise ValueError("UNREVIEWED_CANDIDATE_INCLUDE")
        paths = sorted(lineage.glob.glob(p))
        if not paths:
            raise ValueError("CANDIDATE_INCLUDE_MISSING")
        for _, (d, r) in lineage.collect(paths).items():
            for family in defs:
                defs[family].update(d[family])
                refs[family].update(r[family])
    missing = refs["req"] - defs["req"]
    if len(missing) != 1 or refs["conn"] - defs["conn"]:
        raise ValueError("LIMIT_ZONE_MISSING_SET_CHANGED")
    target = next(iter(missing))
    active = lineage.collect([Path("/etc/nginx/nginx.conf")])
    sources_with_zone = [
        path for path, (d, _) in active.items() if target in d["req"]
    ]
    if (len(sources_with_zone) != 1 or
            lineage.category(sources_with_zone[0], Path("/etc/nginx")) != "NGINX_CONF_D"):
        raise ValueError("LIMIT_ZONE_SOURCE_NOT_UNIQUE")
    source = sources_with_zone[0]
    body = lineage.safe_read(source)
    statement = parse_sanitized_definition(body, target)
    # Pin exact source contents for this execution; refuse concurrent drift.
    sha = hashlib.sha256(body).hexdigest()
    return sources, source, sha, statement

def run_sandbox():
    os.umask(0o077)
    sources, source, source_sha, statement = find_verified_source()
    nginx = shutil.which("nginx")
    openssl = shutil.which("openssl")
    if not nginx or not openssl:
        raise ValueError("ISOLATED_TEST_BINARY_MISSING")
    with tempfile.TemporaryDirectory(prefix="v2-zone-syntax-", dir=syntax.ROOT) as folder:
        temp = Path(folder)
        cert = subprocess.run([
            openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-days", "1", "-keyout", str(temp / "key.pem"),
            "-out", str(temp / "cert.pem"), "-subj", "/CN=localhost",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=25)
        if cert.returncode:
            raise ValueError("SYNTHETIC_CERT_CREATION_FAILED")
        transformed = syntax.prepare(sources, temp)
        if hashlib.sha256(lineage.safe_read(source)).hexdigest() != source_sha:
            raise ValueError("ACTIVE_ZONE_SOURCE_CHANGED_DURING_TEST")
        (temp / "verified-zone.conf").write_text(statement + "\n", encoding="utf-8")
        config = temp / "nginx.conf"
        config.write_text(
            "worker_processes 1;\n"
            "pid " + str(temp / "nginx.pid") + ";\n"
            "error_log " + str(temp / "nginx-error.log") + " warn;\n"
            "events { worker_connections 16; }\n"
            "http {\n"
            "  include " + str(temp / "verified-zone.conf") + ";\n"
            "  include " + str(temp / "main.conf") + ";\n"
            "  include " + str(temp / "test.conf") + ";\n"
            "}\n", encoding="utf-8"
        )
        # Assert provenance and review files still match before nginx -t.
        syntax.inspect_sources()
        checked = subprocess.run([
            nginx, "-t", "-p", str(temp) + "/", "-c", str(config),
            "-e", str(temp / "nginx-error.log"),
        ], capture_output=True, text=True, timeout=25)
        report = {
            "status": ("ISOLATED_V2_NGINX_SYNTAX_PASSED" if checked.returncode == 0
                       else "ISOLATED_V2_NGINX_SYNTAX_FAILED"),
            "nginx_exit_code": checked.returncode,
            "one_active_zone_definition_imported_to_disposable_http": True,
            "source_category": "NGINX_CONF_D",
            "active_zone_source_sha256": source_sha,
            "imported_definition_sha256": hashlib.sha256(statement.encode()).hexdigest(),
            "source_or_zone_name_printed": False,
            "synthetic_tls_only": True,
            "http_security_acceptance_tested": False,
            "production_nginx_installed_or_reloaded": False,
            "b2_or_keycloak_changed": False,
            "release_approved": False,
            "transformed": transformed,
        }
        if checked.returncode:
            message = checked.stderr + "\n" + checked.stdout
            log = temp / "nginx-error.log"
            if log.exists() and log.stat().st_size:
                message += "\n" + syntax.read_regular(log).decode("utf-8", "replace")
            report["sanitized_error"] = syntax.classify_nginx_failure(message)
        return report

if __name__ == "__main__":
    try:
        result = run_sandbox()
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError) as exc:
        # Don't print raw paths or exceptions raised by Nginx/subprocess.
        result = {
            "status": "ISOLATED_V2_ZONE_PRECHECK_BLOCKED",
            "reason": str(exc) if isinstance(exc, ValueError) else type(exc).__name__,
            "production_nginx_installed_or_reloaded": False,
            "release_approved": False,
        }
    print(json.dumps(result, sort_keys=True, indent=2))
    if result["status"] != "ISOLATED_V2_NGINX_SYNTAX_PASSED":
        sys.exit(2)
