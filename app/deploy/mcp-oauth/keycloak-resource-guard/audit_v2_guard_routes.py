#!/usr/bin/env python3
"""Read-only, source-pinned review of V2 Nginx listeners, Host gates and route surface.

Do NOT run/launch nginx or touch production; semantic HTTP/2, IPv6, SNI,
route forwarding and public acceptance remain unproven.
"""
import json
import re
import sys

import isolated_v2_nginx_syntax as pinned

MAX_TOKENS = 40000

def tokenize(raw):
    data = raw.decode("utf-8")
    tokens = []
    buf = []
    quote = None
    esc = False
    comment = False
    def flush():
        if buf:
            tokens.append("".join(buf))
            buf.clear()
    for char in data:
        if comment:
            if char == "\n":
                comment = False
            continue
        if quote:
            if esc:
                buf.append(char)
                esc = False
            elif char == "\\":
                esc = True
            elif char == quote:
                quote = None
            else:
                buf.append(char)
            continue
        if char == "#":
            flush()
            comment = True
        elif char in ('"', "'"):
            quote = char
        elif char in ("{", "}", ";"):
            flush()
            tokens.append(char)
        elif char.isspace():
            flush()
        else:
            buf.append(char)
        if len(tokens) > MAX_TOKENS:
            raise ValueError("NGINX_CONFIG_TOKENS_EXCEEDED")
    flush()
    if quote or esc:
        raise ValueError("UNTERMINATED_NGINX_QUOTE")
    return tokens

def parse(raw):
    tokens = tokenize(raw)
    index = [0]
    def nodes(depth=0):
        if depth > 24:
            raise ValueError("NGINX_CONFIG_NESTING_EXCEEDED")
        output = []
        while index[0] < len(tokens):
            parts = []
            while index[0] < len(tokens) and tokens[index[0]] not in (";", "{", "}"):
                parts.append(tokens[index[0]])
                index[0] += 1
            if index[0] == len(tokens):
                raise ValueError("UNTERMINATED_NGINX_DIRECTIVE")
            end = tokens[index[0]]
            index[0] += 1
            if end == "}":
                if parts or depth == 0:
                    raise ValueError("NGINX_UNEXPECTED_BRACE")
                return output
            if not parts:
                raise ValueError("NGINX_EMPTY_DIRECTIVE")
            if end == "{":
                children = nodes(depth + 1)
            else:
                children = None
            output.append((parts[0], tuple(parts[1:]), children))
        if depth:
            raise ValueError("NGINX_MISSING_CLOSING_BRACE")
        return output
    return nodes()

def walk(nodes):
    for directive in nodes:
        yield directive
        if directive[2] is not None:
            yield from walk(directive[2])

def server_metrics(tree):
    server_nodes = [n for n in tree if n[0] == "server" and n[2] is not None]
    totals = {
        "server_blocks": len(server_nodes),
        "listen_directives": 0,
        "tls_listens": 0,
        "ipv6_listens": 0,
        "http2_mentions": 0,
        "default_server_mentions": 0,
        "exact_locations": 0,
        "prefix_locations": 0,
        "regex_locations": 0,
        "unclassified_locations": 0,
        "unrestricted_api_prefix_location_candidates": 0,
        "locations_total": 0,
        "proxy_pass_directives": 0,
        "explicit_loopback_v2_proxy_pass": 0,
        "non_v2_proxy_pass": 0,
        "host_mismatch_reject_421_mentions": 0,
        "http_host_or_host_expression_mentions": 0,
        "forwarded_host_header_directives": 0,
    }
    for server in server_nodes:
        flat = list(walk(server[2]))
        totals["host_mismatch_reject_421_mentions"] += sum(
            node[0] == "return" and len(node[1]) >= 1 and node[1][0] == "421"
            for node in flat)
        totals["http_host_or_host_expression_mentions"] += sum(
            node[0] in ("if", "map") and
            any("$host" in arg or "$http_host" in arg for arg in node[1])
            for node in flat)
        totals["forwarded_host_header_directives"] += sum(
            node[0] == "proxy_set_header" and len(node[1]) >= 2 and
            node[1][0] == "X-Forwarded-Host" for node in flat)
        for name, args, _ in flat:
            if name == "listen":
                totals["listen_directives"] += 1
                totals["tls_listens"] += "ssl" in args
                totals["ipv6_listens"] += any("[" in v or "::" in v for v in args)
                totals["http2_mentions"] += "http2" in args
                totals["default_server_mentions"] += "default_server" in args
            elif name == "http2" and args and args[0] == "on":
                totals["http2_mentions"] += 1
            elif name == "location":
                totals["locations_total"] += 1
                # A prefix is not automatically unsafe; only a route risk
                # requiring separate semantic/public acceptance.
                if len(args) >= 2 and args[0] == "=":
                    totals["exact_locations"] += 1
                elif args and args[0] in ("~", "~*"):
                    totals["regex_locations"] += 1
                elif args and (args[0] == "^~" or args[0].startswith("/")):
                    totals["prefix_locations"] += 1
                    value = args[1] if args[0] == "^~" and len(args) >= 2 else args[0]
                    totals["unrestricted_api_prefix_location_candidates"] += (
                        value in ("/api", "/api/", "/") )
                else:
                    totals["unclassified_locations"] += 1
            elif name == "proxy_pass":
                totals["proxy_pass_directives"] += 1
                if args == ("http://127.0.0.1:18082",):
                    totals["explicit_loopback_v2_proxy_pass"] += 1
                else:
                    totals["non_v2_proxy_pass"] += 1
    return totals

def inspect(sources=None):
    if sources is None:
        sources = pinned.inspect_sources()
    pair = {}
    for key in ("review_main", "review_test"):
        raw = sources[key]
        if len(raw) > 1024 * 1024:
            raise ValueError("CONFIG_SIZE_OVER_LIMIT")
        pair[key] = server_metrics(parse(raw))
    if pair["review_main"]["server_blocks"] != 2 or pair["review_test"]["server_blocks"] != 2:
        raise ValueError("UNEXPECTED_CANDIDATE_SERVER_LAYOUT")
    if (pair["review_test"]["explicit_loopback_v2_proxy_pass"] != 2
            or b"127.0.0.1:18081" in sources["review_test"]):
        raise ValueError("V2_BACKEND_TARGET_DRIFT")
    if pair["review_main"]["listen_directives"] != 4 or pair["review_test"]["listen_directives"] != 4:
        raise ValueError("UNEXPECTED_LISTENER_COUNT")
    return {
        "status": "PINNED_V2_ROUTE_SURFACE_INVENTORIED",
        "candidate_main": pair["review_main"],
        "candidate_test": pair["review_test"],
        "pinned_source_integrity_verified": True,
        "live_requests_executed": False,
        "nginx_process_launched": False,
        "http_tls_sni_h2_ipv6_behavior_proven": False,
        "proxy_backend_hit": False,
        "public_acceptance_passed": False,
        "guard_install_or_reload_authorized": False,
        "b2_cutover_authorized": False,
    }

if __name__ == "__main__":
    try:
        result = inspect()
    except (UnicodeError, OSError, ValueError) as e:
        result = {"status": "PINNED_V2_ROUTE_INVENTORY_BLOCKED",
                  "reason": str(e) if isinstance(e, ValueError) else type(e).__name__,
                  "guard_install_or_reload_authorized": False}
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "PINNED_V2_ROUTE_SURFACE_INVENTORIED":
        sys.exit(2)
