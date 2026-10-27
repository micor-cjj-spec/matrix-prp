#!/usr/bin/env python3
"""Operator-executed, read-only inventory of NEWDB candidate host conflicts.

Never install, start, stop, reload, change permissions, read environment
secrets, or create files. This is *not* a G0/B2 approval or deployment gate.
No Docker inspect Config.Env and no output of private Docker metadata.
"""
import json
import re
from pathlib import Path
import shutil
import subprocess

PROJECT = "prp-mcp-newdb-review"
PORT = 18083
MIN_AVAILABLE_MEMORY = 2 * 1024**3
MIN_FREE_DISK = 25 * 1024**3
EXPECTED_EXISTING = (
    "prp-mcp-v2-gateway-1",
    "prp-mcp-stage-gateway-1",
)
READ_ONLY_DOCKER_COMMANDS = {
    "containers": ("docker", "ps", "-a", "--format", "{{.Names}}"),
    "published_ports": ("docker", "ps", "--format", "{{.Ports}}"),
    "volumes": ("docker", "volume", "ls", "--format", "{{.Name}}"),
    "networks": ("docker", "network", "ls", "--format", "{{.Name}}"),
}


def tcp_listeners(proc_tcp):
    """Read Linux /proc TCP listener states without binding a socket."""
    lines = proc_tcp.splitlines()
    if not lines or "local_address" not in lines[0] or "st" not in lines[0]:
        raise ValueError("UNRECOGNIZED_PROC_TCP")
    listening = set()
    for row in lines[1:]:
        fields = row.split()
        if len(fields) < 4:
            raise ValueError("MALFORMED_PROC_TCP_ROW")
        local = fields[1]
        if ":" not in local:
            raise ValueError("MALFORMED_LOCAL_ADDRESS")
        try:
            port = int(local.rsplit(":", 1)[1], 16)
        except ValueError:
            raise ValueError("MALFORMED_TCP_PORT") from None
        if fields[3] == "0A":
            listening.add(port)
    return listening


def port_state(proc4, proc6):
    # Absence of IPv6 proc is not enough to conclude no IPv6 listener exists.
    if proc4 is None or proc6 is None:
        return "UNKNOWN_PROC_TCP"
    try:
        occupied = tcp_listeners(proc4) | tcp_listeners(proc6)
    except ValueError:
        return "UNKNOWN_PROC_TCP"
    return "LISTENER_PRESENT" if PORT in occupied else "NO_LISTENER_AT_INVENTORY_TIME"


def docker_port_state(lines):
    """Catch published TCP ports even if Docker disabled userland-proxy.

    In that configuration a host /proc TCP LISTEN socket can be absent
    while iptables DNAT still reserves the exposed Docker published port.
    Never print the source Docker port lists.
    """
    if lines is None:
        return "UNKNOWN_DOCKER_QUERY"
    return ("PUBLISHED_PORT_PRESENT" if any(
        re.search(r"(?<![0-9])18083->[0-9]+/tcp\\b", text)
        for text in lines
    ) else "NO_DOCKER_TCP_PUBLISH_AT_INVENTORY_TIME")


def inventory_state(names, prefix):
    if names is None:
        return "UNKNOWN_DOCKER_QUERY"
    if any(name.startswith(prefix) for name in names):
        return "EXISTING_PROJECT_ARTIFACTS"
    return "NONE_DETECTED"


def analyze(proc4, proc6, containers, volumes, networks, mem_bytes, disk_bytes,
            published_ports=None):
    """Return only coarse metadata, never actual unrelated container names."""
    tcp = port_state(proc4, proc6)
    published = docker_port_state(published_ports)
    container_status = inventory_state(containers, PROJECT + "-")
    volume_status = inventory_state(volumes, PROJECT + "_")
    network_status = inventory_state(networks, PROJECT + "_")
    existing = {}
    for original in EXPECTED_EXISTING:
        existing[original] = (
            "PRESENT" if containers is not None and original in containers
            else "MISSING" if containers is not None else "UNKNOWN_DOCKER_QUERY"
        )
    ram = ("UNKNOWN" if mem_bytes is None
           else "ABOVE_REVIEW_THRESHOLD" if mem_bytes >= MIN_AVAILABLE_MEMORY
           else "BELOW_REVIEW_THRESHOLD")
    disk = ("UNKNOWN" if disk_bytes is None
            else "ABOVE_REVIEW_THRESHOLD" if disk_bytes >= MIN_FREE_DISK
            else "BELOW_REVIEW_THRESHOLD")
    no_collision = (
        tcp == "NO_LISTENER_AT_INVENTORY_TIME"
        and published == "NO_DOCKER_TCP_PUBLISH_AT_INVENTORY_TIME"
        and container_status == "NONE_DETECTED"
        and volume_status == "NONE_DETECTED"
        and network_status == "NONE_DETECTED"
        and all(x == "PRESENT" for x in existing.values())
        and ram == disk == "ABOVE_REVIEW_THRESHOLD"
    )
    return {
        "target": {
            "project": PROJECT,
            "loopback_port": "127.0.0.1:18083",
            "database": "matrix_prp_mcp_newdb_review",
            "mysql_volume": "prp-mcp-newdb-review_newdb_mysql",
        },
        "host_observations": {
            "tcp_port_18083": tcp,
            "docker_published_tcp_18083": published,
            "project_containers": container_status,
            "project_volumes": volume_status,
            "project_networks": network_status,
            "existing_gateway_names": existing,
            "available_memory": ram,
            "free_disk": disk,
        },
        "newdb_host_preflight": (
            "NO_COLLISION_OBSERVED_REVIEW_ONLY" if no_collision
            else "BLOCKED_OR_UNVERIFIED"
        ),
        "inventory_is_a_point_in_time": True,
        "independent_g0_approval": "NOT_ESTABLISHED_BY_THIS_SCRIPT",
        "b2_authorization": "NOT_ESTABLISHED_BY_THIS_SCRIPT",
        "deployment_permitted": False,
        "no_host_mutation_performed": True,
    }


def docker_names(key):
    try:
        result = subprocess.run(
            READ_ONLY_DOCKER_COMMANDS[key], check=False, capture_output=True,
            text=True, timeout=15)
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return set(filter(None, result.stdout.splitlines()))


def read_proc(path):
    try:
        return Path(path).read_text(encoding="ascii")
    except (OSError, UnicodeError):
        return None


def available_mem_bytes():
    try:
        lines = Path("/proc/meminfo").read_text(encoding="ascii").splitlines()
        value = next(x.split(":", 1)[1].strip().split()
                     for x in lines if x.startswith("MemAvailable:"))
        if len(value) != 2 or value[1] != "kB":
            return None
        return int(value[0]) * 1024
    except (OSError, UnicodeError, StopIteration, ValueError):
        return None


def free_disk_bytes():
    try:
        return shutil.disk_usage("/").free
    except OSError:
        return None


def main():
    report = analyze(
        read_proc("/proc/net/tcp"), read_proc("/proc/net/tcp6"),
        docker_names("containers"), docker_names("volumes"),
        docker_names("networks"), available_mem_bytes(), free_disk_bytes(),
        docker_names("published_ports"),
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    # A successful read is NOT a deployment-ready exit code. There is no
    # write/approval path in this file or its output.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
