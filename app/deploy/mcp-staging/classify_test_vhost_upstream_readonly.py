#!/usr/bin/env python3
"""Read-only classification of an on-disk Nginx test-vhost from nginx -T.

This checks candidate upstream references in the currently readable config.
It does NOT prove the running workers loaded that config, resolve Nginx
location precedence, identify the live upstream, or authorize a release.
Never prints any raw nginx configuration, stderr, secrets, or OAuth data.
"""
import json
import re
import subprocess

TARGET = "/etc/nginx/conf.d/prp-mcp-test.conf"
MAX_DUMP_BYTES = 4 * 1024 * 1024
SECTIONS = re.compile(r"(?m)^# configuration file ([^\r\n:]+):[ \t]*$")
SERVER_NAME = re.compile(r"(?m)^[ \t]*server_name[ \t]+prp-test\.micor\.top[ \t]*;")
PROXY_PASS = re.compile(r"(?m)^[ \t]*proxy_pass[ \t]+([^;\s]+)[ \t]*;")
EXPECTED_V2 = "http://127.0.0.1:18082"
LEGACY = "http://127.0.0.1:18081"


def unknown(reason):
    return {
        "diagnostic_only": True,
        "on_disk_vhost": reason,
        "candidate_upstream": "UNVERIFIED",
        "live_upstream": "NOT_PROVEN",
        "effective_oauth_scopes": "NOT_CHECKED",
        "host_mutated": False,
        "release_approved": False,
    }


def classify(dump):
    """Summarize direct proxy_pass literals without exposing any config text."""
    if not isinstance(dump, bytes) or len(dump) > MAX_DUMP_BYTES:
        return unknown("DUMP_INVALID_OR_TOO_LARGE")
    try:
        source = dump.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return unknown("DUMP_ENCODING_UNVERIFIED")
    hits = list(SECTIONS.finditer(source))
    sections = [
        source[match.end() : hits[i + 1].start() if i + 1 < len(hits) else len(source)]
        for i, match in enumerate(hits)
        if match.group(1) == TARGET
    ]
    if len(sections) != 1:
        return unknown("TARGET_VHOST_NOT_UNIQUE_OR_MISSING")
    body = sections[0]
    if not SERVER_NAME.search(body):
        return unknown("EXPECTED_TEST_HOST_NOT_FOUND")
    passes = PROXY_PASS.findall(body)
    if not passes:
        return unknown("NO_LITERAL_PROXY_PASS_IN_TEST_VHOST")
    if any(value not in (EXPECTED_V2, LEGACY) for value in passes):
        return unknown("COMPLEX_OR_NONSTANDARD_PROXY_PRESENT")
    ports = set(passes)
    if ports == {EXPECTED_V2}:
        candidate = "V2_18082_ONLY_IN_ON_DISK_VHOST"
    elif ports == {LEGACY}:
        candidate = "LEGACY_18081_ONLY_IN_ON_DISK_VHOST"
    else:
        candidate = "MIXED_18081_18082_IN_ON_DISK_VHOST"
    result = unknown("TEST_VHOST_FOUND_IN_NGINX_T")
    result["candidate_upstream"] = candidate
    result["direct_proxy_pass_count"] = len(passes)
    result["route_precedence_checked"] = False
    result["included_proxy_chain_checked"] = False
    return result


def main():
    try:
        # nginx -T validates and dumps the files on disk, not running-worker memory.
        check = subprocess.run(["nginx", "-T"], capture_output=True, timeout=15,
                               check=False)
    except (OSError, subprocess.TimeoutExpired):
        result = unknown("NGINX_T_UNAVAILABLE")
    else:
        result = (classify(check.stdout) if check.returncode == 0
                  else unknown("NGINX_T_REJECTED_CONFIG"))
    print(json.dumps(result, sort_keys=True))
    # Ambiguous or legacy references are findings, never silent acceptance.
    return 0 if result["candidate_upstream"].startswith("V2_") else 2


if __name__ == "__main__":
    raise SystemExit(main())
