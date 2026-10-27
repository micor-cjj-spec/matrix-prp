#!/usr/bin/env python3
"""Offline, SHA-pinned, route-level V2 Nginx guard review.

Does not execute nginx, touch traffic or approve installation. All output is
aggregated; private server names, paths, zone keys and route values stay hidden.
"""
import json
import re
import sys

import audit_v2_guard_routes as audit
import isolated_v2_nginx_syntax as pinned

BROAD_PATHS = {"/", "/api", "/api/", "/prp", "/prp/"}
HOP = re.compile(r"^https?://(?:(?:127\.0\.0\.1)|(?:\[::1\])):\d+(?:/.*)?$", re.I)

def route_info(location):
    _, args, children = location
    if children is None or not args:
        raise ValueError("INVALID_LOCATION_SHAPE")
    if args[0] in ("=", "^~", "~", "~*"):
        if len(args) != 2:
            raise ValueError("UNEXPECTED_LOCATION_ARGUMENTS")
        mode, path = args[0], args[1]
    else:
        if len(args) != 1:
            raise ValueError("UNEXPECTED_LOCATION_ARGUMENTS")
        mode, path = "prefix", args[0]
    if mode in ("=", "^~", "prefix") and not path.startswith("/"):
        raise ValueError("UNEXPECTED_LOCATION_PATH")
    nodes = list(audit.walk(children))
    proxies = [x for x in nodes if x[0] in (
        "proxy_pass", "grpc_pass", "uwsgi_pass", "fastcgi_pass", "scgi_pass")]
    returns = [x for x in nodes if x[0] == "return"]
    invalid_proxy = [
        x for x in proxies if len(x[1]) != 1 or
        not HOP.fullmatch(x[1][0])
    ]
    v2 = [x for x in proxies if x[1] == ("http://127.0.0.1:18082",)]
    if invalid_proxy:
        # Keep inventory diagnostic-only. No backend values exposed.
        upstream_class = "UNREVIEWED_OR_VARIABLE"
    else:
        upstream_class = "LOOPBACK_ONLY" if proxies else "NO_UPSTREAM"
    return {
        "exact": mode == "=",
        "regex": mode in ("~", "~*"),
        "broad": mode not in ("~", "~*") and path in BROAD_PATHS,
        "v2": len(v2),
        "proxy": len(proxies),
        "other_proxy": len(proxies) - len(v2),
        "unsafe": len(invalid_proxy),
        "returns_421": sum(x[1] and x[1][0] == "421" for x in returns),
        "returns_403_or_404": sum(x[1] and x[1][0] in ("403", "404") for x in returns),
        "upstream_class": upstream_class,
        "rewrite": sum(x[0] in ("rewrite", "try_files", "error_page")
                       for x in nodes),
        "mcp_shape": (
            "EXACT_OAUTH_DISCOVERY" if mode == "=" and
            (path.startswith("/.well-known/") or "/.well-known/" in path) else
            "EXACT_MCP" if mode == "=" and path == "/api/mcp" else
            "EXACT_MCP_LINK" if mode == "=" and path == "/api/mcp/link" else
            "OTHER"
        ),
    }

def inspect(sources=None):
    if sources is None:
        sources = pinned.inspect_sources()
    baseline = audit.inspect(sources)
    result = {}
    for key in ("review_main", "review_test"):
        tree = audit.parse(sources[key])
        server_blocks = [x for x in tree if x[0] == "server"]
        if len(server_blocks) != 2:
            raise ValueError("VHOST_COUNT_DRIFT")
        items = []
        for server in server_blocks:
            for node in audit.walk(server[2]):
                if node[0] == "location":
                    items.append(route_info(node))
        total_v2 = sum(r["v2"] for r in items)
        stats = {
            "locations_checked": len(items),
            "v2_proxy_locations": sum(r["v2"] > 0 for r in items),
            "v2_proxy_directives": total_v2,
            "v2_behind_exact_locations": sum(r["v2"] for r in items if r["exact"]),
            "v2_behind_non_exact_locations": sum(r["v2"] for r in items if not r["exact"]),
            "broad_prefix_locations": sum(r["broad"] for r in items),
            "broad_prefix_with_proxy": sum(r["broad"] and r["proxy"] > 0 for r in items),
            "broad_prefix_returning_403_404": sum(r["broad"] and r["returns_403_or_404"] > 0 for r in items),
            "broad_prefix_returning_421": sum(r["broad"] and r["returns_421"] > 0 for r in items),
            "nonloopback_or_variable_upstream_directives": sum(r["unsafe"] for r in items),
            "other_upstream_directives": sum(r["other_proxy"] for r in items),
            "mcp_exact_location_blocks": sum(r["mcp_shape"] == "EXACT_MCP" for r in items),
            "oauth_discovery_exact_location_blocks": sum(r["mcp_shape"] == "EXACT_OAUTH_DISCOVERY" for r in items),
            "mcp_link_exact_location_blocks": sum(r["mcp_shape"] == "EXACT_MCP_LINK" for r in items),
            "regex_locations_with_upstreams": sum(r["regex"] and r["proxy"] > 0 for r in items),
            "rewrite_or_try_files_directives_in_locations": sum(r["rewrite"] for r in items),
        }
        if len(items) != baseline["candidate_main" if key == "review_main" else "candidate_test"]["locations_total"]:
            raise ValueError("LOCATION_COUNT_DRIFT")
        if key == "review_test" and total_v2 != 2:
            raise ValueError("TEST_V2_TARGET_COUNT_DRIFT")
        result["main" if key == "review_main" else "test"] = stats

    # Failure-to-prove is not approval: unexpected layout only blocks future
    # runtime testing and never implies a known exploit on live production.
    findings = []
    if result["test"]["v2_behind_non_exact_locations"]:
        findings.append("V2_TARGET_NOT_EXCLUSIVELY_EXACT_MATCHED")
    if result["test"]["nonloopback_or_variable_upstream_directives"]:
        findings.append("TEST_UPSTREAM_TARGETS_REQUIRE_MANUAL_REVIEW")
    if result["main"]["broad_prefix_with_proxy"] or result["test"]["broad_prefix_with_proxy"]:
        findings.append("BROAD_PREFIX_PROXY_REQUIRES_AUTHORIZATION_REVIEW")
    if baseline["candidate_test"]["http2_mentions"] == 0:
        findings.append("TEST_VHOST_HTTP2_NOT_EXPLICITLY_DECLARED")
    return {
        "status": "V2_ROUTE_SEMANTICS_INVENTORIED",
        "source_sha256_verified": True,
        "main": result["main"],
        "test": result["test"],
        "findings": findings,
        "production_nginx_tested_or_modified": False,
        "upstream_or_api_request_executed": False,
        "security_runtime_acceptance_passed": False,
        "guard_install_or_reload_authorized": False,
        "b2_cutover_authorized": False,
    }

if __name__ == "__main__":
    try:
        value = inspect()
    except (OSError, UnicodeError, ValueError) as exc:
        value = {
            "status": "V2_ROUTE_SEMANTICS_BLOCKED",
            "reason": str(exc) if isinstance(exc, ValueError) else type(exc).__name__,
            "guard_install_or_reload_authorized": False,
        }
    print(json.dumps(value, indent=2, sort_keys=True))
    if value["status"] != "V2_ROUTE_SEMANTICS_INVENTORIED":
        sys.exit(2)
