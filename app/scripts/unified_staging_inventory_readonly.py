#!/usr/bin/env python3
"""S0 PRP environment inventory: operator-run, read-only, privacy-minimizing.

This tool does NOT contact a server. It may be run only by an authorized
operator ON the specifically approved host. It never installs or changes
Docker, DNS, Nginx, MySQL, Keycloak, volumes, files or permissions.
Absence of a listener/name is NOT proof that a port is free or safe to use.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

PORTS = (11000, 18081, 18082, 18083)
PROJECT_HINTS = {
    "production_name_hint": "matrix-prp",
    "legacy_18081_name_hint": "prp-mcp-stage",
    "v2_18082_name_hint": "prp-mcp-v2",
    "newdb_18083_name_hint": "prp-mcp-newdb-review",
    "unified_stage_candidate_hint": "prp-unified-stage",
}
DOCKER_COMMANDS = {
    "containers": ("docker", "ps", "-a", "--format", "{{.Names}}"),
    "published_ports": ("docker", "ps", "--format", "{{.Ports}}"),
    "volumes": ("docker", "volume", "ls", "--format", "{{.Name}}"),
    "networks": ("docker", "network", "ls", "--format", "{{.Name}}"),
}
SAFE_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}
MAX_DOCKER_STDOUT = 128 * 1024


def listeners(raw):
    """Parse /proc/net/tcp[6] into port numbers, or return None on bad input."""
    if raw is None:
        return None
    lines = raw.splitlines()
    if not lines or "local_address" not in lines[0] or "st" not in lines[0]:
        return None
    result = set()
    for line in lines[1:]:
        fields = line.split()
        if len(fields) < 4 or ":" not in fields[1]:
            return None
        try:
            port = int(fields[1].rsplit(":", 1)[1], 16)
        except ValueError:
            return None
        if not 0 <= port <= 65535:
            return None
        if fields[3] == "0A":
            result.add(port)
    return result


def name_state(names, prefix):
    if names is None:
        return "UNKNOWN_QUERY"
    # Only a fixed project hint is emitted; never expose unrelated names.
    return ("NAME_MATCH_OBSERVED" if any(
        name == prefix or name.startswith(prefix + "-") or
        name.startswith(prefix + "_") for name in names
    ) else "NO_NAME_MATCH_OBSERVED")


def published_state(lines, port):
    if lines is None:
        return "UNKNOWN_QUERY"
    # Detect Docker NAT port publishes even when /proc does not show a proxy.
    return ("PUBLISHED_TCP_OBSERVED" if any(
        re.search(r"(?<!\d)" + str(port) + r"->\d+/tcp\b", line)
        for line in lines
    ) else "NO_PUBLISH_OBSERVED")


def capacity_state(free_bytes, threshold):
    if free_bytes is None or free_bytes < 0:
        return "UNKNOWN"
    return "ABOVE_REVIEW_THRESHOLD" if free_bytes >= threshold else "BELOW_REVIEW_THRESHOLD"


def analyze(proc4, proc6, containers, published, volumes, networks,
            free_memory, free_disk, observed_utc):
    a, b = listeners(proc4), listeners(proc6)
    tcp = a | b if a is not None and b is not None else None
    ports = {
        str(port): {
            "host_tcp": ("UNKNOWN" if tcp is None else
                         "LISTENER_OBSERVED" if port in tcp else
                         "NO_LISTENER_OBSERVED"),
            "docker_tcp_publish": published_state(published, port),
        }
        for port in PORTS
    }
    # Counts, names, mounts, command outputs, secrets and raw config stay local.
    projects = {
        key: {
            "containers": name_state(containers, prefix),
            "volumes": name_state(volumes, prefix),
            "networks": name_state(networks, prefix),
        }
        for key, prefix in PROJECT_HINTS.items()
    }
    return {
        "schema_version": 1,
        "observed_utc": observed_utc,
        "scope": "POINT_IN_TIME_READ_ONLY_METADATA",
        "ports": ports,
        "project_name_hints": projects,
        "capacity": {
            "available_memory_2gib": capacity_state(free_memory, 2 * 1024**3),
            "root_free_disk_25gib": capacity_state(free_disk, 25 * 1024**3),
            "thresholds_are_heuristics_not_sizing_approval": True,
        },
        "host_identity_verified": False,
        "docker_metadata_proves_ownership": False,
        "dns_tls_keycloak_database_flyway_verified": False,
        "staging_deployment_authorized": False,
        "production_deployment_authorized": False,
        "new_stage_ready": "NOT_ESTABLISHED",
        "absence_is_not_availability_proof": True,
    }


def read_proc(path):
    try:
        return Path(path).read_text(encoding="ascii")
    except (OSError, UnicodeError):
        return None


def docker_lines(key):
    try:
        completed = subprocess.run(
            DOCKER_COMMANDS[key], check=False, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            env=SAFE_ENV, timeout=12,
        )
        if completed.returncode != 0 or len(completed.stdout) > MAX_DOCKER_STDOUT:
            return None
        return set(filter(None, completed.stdout.decode("utf-8").splitlines()))
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        return None


def available_memory():
    raw = read_proc("/proc/meminfo")
    if raw is None:
        return None
    match = re.search(r"^MemAvailable:\s+(\d+) kB$", raw, re.M)
    return int(match.group(1)) * 1024 if match else None


def disk_free():
    try:
        return shutil.disk_usage("/").free
    except OSError:
        return None


def main():
    # No caller-controlled flags, paths, commands, hostnames or destinations.
    if len(sys.argv) != 1 or os.name != "posix":
        return 2
    report = analyze(
        read_proc("/proc/net/tcp"), read_proc("/proc/net/tcp6"),
        docker_lines("containers"), docker_lines("published_ports"),
        docker_lines("volumes"), docker_lines("networks"),
        available_memory(), disk_free(),
        datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )
    print(json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
