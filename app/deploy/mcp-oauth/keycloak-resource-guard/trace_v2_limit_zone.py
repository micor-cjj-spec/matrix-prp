#!/usr/bin/env python3
"""Read-only trace of ONE missing Nginx limit_req_zone across pinned V2 review
files and active, included Nginx configs.

No subprocess, nginx -T, activation, reload, user data or secret value output.
Classifies include provenance; never prints config, zone names, or paths.
"""
import glob
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

REVIEW = Path("/root/prp-mcp-cimd-stage-b/review-only-v2-guard-20261026-01")
SOURCES = {
    "active_main": (Path("/etc/nginx/conf.d/micor.top.conf"),
                    "ba200a57e880dd286789fcb04ffcf7ce76db4f6005e86bdf934fc9682807792b"),
    "active_test": (Path("/etc/nginx/conf.d/prp-mcp-test.conf"),
                    "35bb31322b23efef536c97e12619ceac7087aa4cf2d56c57f3307232f9362397"),
    "review_main": (REVIEW / "micor.top.guard-v2.REVIEW.conf",
                    "da227c0f6be8c9342d8830cbbe2e76372e4083bff51768c490a0e60c6b18828b"),
    "review_test": (REVIEW / "prp-test.guard-v2.REVIEW.conf",
                    "728b4a3290353f90ea692a2e1ae38a1656101e4381ee3bbdbce6c1cb80964421"),
}
DIRECTIVE = re.compile(
    r"(?m)(?:(?<=^)|(?<=[;{}]))[ \t]*"
    r"(limit_req_zone|limit_conn_zone|limit_req|limit_conn|include)[ \t]+"
    r"([^;{}]*);")
ZONE = re.compile(r"(?:^|\s)zone=([A-Za-z0-9_.-]+)(?::[0-9]+[kKmMgG]?)?(?:\s|$)")
FIRST = re.compile(r"^([A-Za-z0-9_.-]+)(?:\s|$)")
MAX_FILES = 120
MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 6 * MAX_FILE_BYTES

def safe_read(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_FILE_BYTES:
            raise ValueError("INPUT_NOT_BOUNDED_REGULAR_FILE")
        with os.fdopen(os.dup(fd), "rb") as stream:
            body = stream.read(MAX_FILE_BYTES + 1)
        if len(body) != info.st_size:
            raise ValueError("INPUT_CHANGED_WHILE_READING")
        return body
    finally:
        os.close(fd)

def parse_config(raw):
    """List only zoned definitions/references and include patterns; drop comments."""
    plain = "\n".join(line.split("#", 1)[0] for line in
                      raw.decode("utf-8").splitlines())
    defs = {"req": set(), "conn": set()}
    refs = {"req": set(), "conn": set()}
    includes = []
    for found in DIRECTIVE.finditer(plain):
        kind, value = found.group(1), found.group(2).strip()
        if kind == "include":
            includes.append(value)
            continue
        if kind == "limit_conn":
            match = FIRST.match(value)
        else:
            match = ZONE.search(" " + value + " ")
        if match is None:
            raise ValueError("UNRECOGNIZED_LIMIT_DIRECTIVE")
        name = match.group(1)
        family = "req" if "req" in kind else "conn"
        (defs if kind.endswith("_zone") else refs)[family].add(name)
    return defs, refs, includes

def category(path, base):
    path = path.resolve(strict=True)
    if path == base / "nginx.conf":
        return "NGINX_ROOT"
    if (base / "conf.d") in path.parents:
        return "NGINX_CONF_D"
    if (base / "sites-enabled") in path.parents:
        return "NGINX_SITES_ENABLED"
    if (base / "sites-available") in path.parents:
        return "NGINX_SITES_AVAILABLE"
    if (base / "snippets") in path.parents:
        return "NGINX_SNIPPET"
    return "OTHER_NGINX_INCLUDE"

def collect(start_paths, *, base=Path("/etc/nginx")):
    """Bounded include walker; aborts entire scan on any unknown include."""
    base = base.resolve(strict=True)
    visited = {}
    stack = list(start_paths)
    budget = 0
    while stack:
        supplied = Path(stack.pop())
        resolved = supplied.resolve(strict=True)
        if resolved in visited:
            continue
        if resolved != base / "nginx.conf" and resolved.suffix not in (".conf", ".types"):
            raise ValueError("INCLUDE_UNREVIEWED_FILE_TYPE")
        if not resolved.is_relative_to(base):
            raise ValueError("INCLUDE_OUTSIDE_NGINX_TREE")
        if len(visited) >= MAX_FILES:
            raise ValueError("INCLUDE_FILE_COUNT_EXCEEDED")
        raw = safe_read(resolved)
        budget += len(raw)
        if budget > MAX_TOTAL_BYTES:
            raise ValueError("INCLUDE_SIZE_BUDGET_EXCEEDED")
        defs, refs, includes = parse_config(raw)
        visited[resolved] = (defs, refs)
        for pattern in includes:
            if any(x in pattern for x in ("\n", "\r", '"', "'", "$", "\\", "..")):
                raise ValueError("UNSAFE_INCLUDE_PATTERN")
            if not pattern.startswith("/"):
                pattern = str(base / pattern)
            if not (pattern == str(base) or pattern.startswith(str(base) + "/")):
                raise ValueError("INCLUDE_OUTSIDE_NGINX_TREE")
            expanded = sorted(glob.glob(pattern))
            if len(expanded) > MAX_FILES:
                raise ValueError("INCLUDE_GLOB_TOO_BROAD")
            if not expanded and not any(c in pattern for c in "*?["):
                raise ValueError("REQUIRED_INCLUDE_MISSING")
            stack.extend(Path(p) for p in expanded)
    return visited

def inspect(sources=None, *, active_root=Path("/etc/nginx/nginx.conf"),
            base=Path("/etc/nginx")):
    if sources is None:
        sources = {}
        for name, (path, pinned_hash) in SOURCES.items():
            body = safe_read(path)
            if hashlib.sha256(body).hexdigest() != pinned_hash:
                raise ValueError("PINNED_CONFIG_DRIFT_" + name.upper())
            sources[name] = body
    defs = {"req": set(), "conn": set()}
    refs = {"req": set(), "conn": set()}
    review_includes = []
    for name in ("review_main", "review_test"):
        d, r, inc = parse_config(sources[name])
        for family in defs:
            defs[family].update(d[family])
            refs[family].update(r[family])
        review_includes.extend(inc)
    if review_includes:
        # The prior isolated syntax test included these very files.
        # Only scan Nginx-controlled, regular configuration dependencies.
        paths = []
        for pattern in review_includes:
            if not pattern.startswith(str(base) + "/") or ".." in pattern:
                raise ValueError("CANDIDATE_INCLUDE_NOT_APPROVED")
            paths.extend(Path(p) for p in sorted(glob.glob(pattern)))
        if not paths:
            raise ValueError("CANDIDATE_INCLUDE_MISSING")
        for _, (d, r) in collect(paths, base=base).items():
            for family in defs:
                defs[family].update(d[family])
                refs[family].update(r[family])
    missing = refs["req"] - defs["req"]
    if len(missing) != 1:
        raise ValueError("EXPECTED_EXACTLY_ONE_MISSING_REQUEST_ZONE")

    active = collect([active_root], base=base)
    target = next(iter(missing))
    occurrences = {}
    for path, (d, _) in active.items():
        if target in d["req"]:
            kind = category(path, base.resolve(strict=True))
            occurrences[kind] = occurrences.get(kind, 0) + 1
    status = ("MISSING_ZONE_DEFINED_IN_ACTIVE_INCLUDE_GRAPH"
              if occurrences else "MISSING_ZONE_NOT_DEFINED_IN_ACTIVE_INCLUDE_GRAPH")
    return {
        "status": status,
        "pinned_candidate_sources_verified": True,
        "candidate_req_zone_missing_count": len(missing),
        "candidate_conn_zone_missing_count": len(refs["conn"] - defs["conn"]),
        "active_include_graph_scanned": True,
        "active_config_files_scanned": len(active),
        "matching_definition_locations": occurrences,
        "matching_definition_count": sum(occurrences.values()),
        "zone_name_or_config_content_printed": False,
        "nginx_test_or_reload_executed": False,
        "release_approved": False,
    }

if __name__ == "__main__":
    try:
        result = inspect()
    except (OSError, UnicodeError, ValueError) as exc:
        result = {
            "status": "READ_ONLY_ZONE_LINEAGE_BLOCKED",
            "reason": str(exc) if isinstance(exc, ValueError) else type(exc).__name__,
            "nginx_test_or_reload_executed": False,
            "release_approved": False,
        }
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] == "READ_ONLY_ZONE_LINEAGE_BLOCKED":
        sys.exit(2)
