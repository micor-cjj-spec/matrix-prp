#!/usr/bin/env python3
"""Review-only V2 raw URI guard overlay for disposable Nginx HTTP tests.

The SHA-pinned candidate files remain untouched. Only the private temporary
test.conf inside the isolated netns may receive this diagnostic overlay.
Never install or authorize an Nginx change from this module.
"""
from collections import Counter
import re

import audit_v2_guard_routes as audit

OPEN = re.compile(
    r"(?m)^([ \t]*)location[ \t]+=[ \t]+"
    r"(/[A-Za-z0-9_./-]+)[ \t]*\{"
)
LOOPBACK_MCP = ("http://127.0.0.1:18082",)

def exact_locations_and_targets(raw):
    """Validate all exact locations and identify exactly two V2 routes."""
    tree = audit.parse(raw)
    exact_paths, protected = [], []
    for server in tree:
        if server[0] != "server" or server[2] is None:
            raise ValueError("UNEXPECTED_CANDIDATE_CONFIG_LAYOUT")
        for node in audit.walk(server[2]):
            name, args, children = node
            if name != "location" or not args or args[0] != "=":
                continue
            if len(args) != 2 or children is None:
                raise ValueError("UNREVIEWED_EXACT_LOCATION")
            path = args[1]
            exact_paths.append(path)
            forwards = [item for item in audit.walk(children)
                        if item[0] == "proxy_pass" and item[1] == LOOPBACK_MCP]
            if forwards:
                if len(forwards) != 1:
                    raise ValueError("UNEXPECTED_MULTIPLE_V2_PROXIES_IN_LOCATION")
                protected.append(path)
    if len(protected) != 2:
        raise ValueError("EXACT_TWO_V2_PROXY_LOCATIONS_REQUIRED")
    if len(set(protected)) != 2:
        raise ValueError("V2_PROXY_LOCATION_PATHS_NOT_UNIQUE")
    if any(not re.fullmatch(r"/[A-Za-z0-9_./-]+", item)
           for item in exact_paths):
        raise ValueError("UNREVIEWED_EXACT_LOCATION_PATH")
    return exact_paths, protected

def overlay(raw):
    """Return only a guarded ephemeral test.conf and aggregate counts."""
    paths, protected = exact_locations_and_targets(raw)
    text = raw.decode("utf-8")
    found = [match.group(2) for match in OPEN.finditer(text)]
    if Counter(found) != Counter(paths):
        raise ValueError("EXACT_LOCATION_SOURCE_SCAN_MISMATCH")
    guard_count = 0
    def insert(match):
        nonlocal guard_count
        indent, path = match.group(1), match.group(2)
        if path not in protected:
            return match.group(0)
        guard_count += 1
        # Request URI is unnormalized while location matching is normalized.
        # Query strings are deliberately rejected in this exploratory test.
        return (match.group(0) + "\n" + indent +
                "    if ($request_uri != " + path + ") { return 404; }")
    rewritten = OPEN.sub(insert, text)
    if guard_count != 2 or len(rewritten) <= len(text):
        raise ValueError("EXPECTED_TWO_DISPOSABLE_RAW_URI_GUARDS")
    for path in protected:
        raw_check = "if ($request_uri != " + path + ") { return 404; }"
        if rewritten.count(raw_check) != 1:
            raise ValueError("RAW_URI_GUARD_DUPLICATE_OR_MISSING")
    return rewritten.encode("utf-8"), {
        "raw_uri_guards_inserted_in_disposable_vhost": guard_count,
        "query_strings_allowed_in_experiment": False,
        "original_candidate_modified": False,
        "production_nginx_changed": False,
        "release_approved": False,
    }
