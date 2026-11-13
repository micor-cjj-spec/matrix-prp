#!/usr/bin/env python3
"""Safe read-only production capacity snapshot for PRP's existing JVM.

Uses /proc, statvfs and selected systemctl show properties. Does not access
environment variables, command lines, logs, secrets, tokens, MySQL tables or
Docker sockets; does not start/stop/reload anything. Never asserts deploy-safe.
"""
import argparse
import json
import os
import re
import subprocess
from pathlib import Path

MEMORY_FIELDS = frozenset((
    "MemTotal", "MemAvailable", "SwapTotal", "SwapFree",
    "Cached", "SReclaimable", "Shmem",
))
PROCESS_FIELDS = frozenset(("VmRSS", "VmHWM", "VmSize", "Threads"))
SYSTEMD_FIELDS = frozenset((
    "MainPID", "ActiveState", "SubState", "MemoryCurrent",
    "MemoryMax", "TasksCurrent",
))


def parse_memory(text):
    """Parse only a whitelisted aggregate from /proc/meminfo."""
    result = {}
    for line in text.splitlines():
        match = re.fullmatch(r"([A-Za-z_]+):\s*(\d+)\s*(kB)?", line.strip())
        if match and match.group(1) in MEMORY_FIELDS:
            result[match.group(1)] = int(match.group(2))  # meminfo uses KiB
    if not {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"} <= result.keys():
        raise ValueError("Required /proc/meminfo counters unavailable")
    if result["MemAvailable"] > result["MemTotal"] or result["SwapFree"] > result["SwapTotal"]:
        raise ValueError("Host memory counters inconsistent")
    return result


def parse_status(text):
    """Read only process memory and thread counters, never names or args."""
    result = {}
    for line in text.splitlines():
        match = re.fullmatch(r"(VmRSS|VmHWM|VmSize|Threads):\s*(\d+)\s*(kB)?", line.strip())
        if match:
            result[match.group(1)] = int(match.group(2))
    return result


def parse_systemd(text):
    """Allowlist the exact unit properties; reject malformed PID."""
    result = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        name, val = line.split("=", 1)
        if name in SYSTEMD_FIELDS:
            result[name] = val
    pid = result.get("MainPID", "0")
    if not pid.isdecimal() or int(pid) > 2**31 - 1:
        raise ValueError("Invalid systemd main process ID")
    return result


def safe_int(value):
    try:
        if value in (None, "", "[not set]", "infinity", "18446744073709551615"):
            return None
        result = int(value)
        return result if 0 <= result < 2**63 - 1 else None
    except (TypeError, ValueError):
        return None


def snapshot(*, unit="matrix-prp.service", proc_root="/proc", stat_path="/", systemctl=None):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,95}\.service", unit):
        raise ValueError("Use an explicit systemd service unit, not a command")
    proc = Path(proc_root)
    mem = parse_memory((proc / "meminfo").read_text(encoding="ascii"))
    if systemctl is None:
        def systemctl(command):
            return subprocess.run(
                command, check=True, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, timeout=8).stdout
    unit_data = parse_systemd(systemctl([
        "systemctl", "show", unit, "--no-pager",
        "--property=" + ",".join(sorted(SYSTEMD_FIELDS))
    ]))
    pid = int(unit_data.get("MainPID", "0"))
    proc_data = {}
    if pid > 0:
        try:
            proc_data = parse_status((proc / str(pid) / "status").read_text(encoding="utf-8"))
        except (FileNotFoundError, PermissionError):
            pass
    # MB is IEC MiB, not SI megabytes. Avoid printing service command lines.
    disk = os.statvfs(stat_path)
    try:
        load1 = float((proc / "loadavg").read_text(encoding="ascii").split()[0])
    except (OSError, ValueError, IndexError):
        load1 = None
    return {
        "host": {
            "total_mib": round(mem["MemTotal"] / 1024, 1),
            "available_mib": round(mem["MemAvailable"] / 1024, 1),
            "swap_total_mib": round(mem["SwapTotal"] / 1024, 1),
            "swap_free_mib": round(mem["SwapFree"] / 1024, 1),
            "load1": load1,
            "disk_free_gib": round(disk.f_bavail * disk.f_frsize / (1024**3), 1),
        },
        "prp": {
            "active_state": unit_data.get("ActiveState", "unknown"),
            "sub_state": unit_data.get("SubState", "unknown"),
            "main_pid_present": pid > 0,  # pid never exposed
            "rss_mib": round(proc_data["VmRSS"] / 1024, 1) if "VmRSS" in proc_data else None,
            "rss_peak_mib": round(proc_data["VmHWM"] / 1024, 1) if "VmHWM" in proc_data else None,
            "threads": proc_data.get("Threads"),
            "systemd_memory_mib": (
                round(safe_int(unit_data["MemoryCurrent"]) / (1024**2), 1)
                if safe_int(unit_data.get("MemoryCurrent")) is not None else None
            ),
            "systemd_memory_limit_mib": (
                round(safe_int(unit_data["MemoryMax"]) / (1024**2), 1)
                if safe_int(unit_data.get("MemoryMax")) is not None else None
            ),
        },
    }


def assess(measurement, minimum_available_mib=1536, minimum_disk_gib=10):
    host = measurement["host"]
    service = measurement["prp"]
    warnings = []
    if service["active_state"] != "active" or not service["main_pid_present"]:
        warnings.append("PRP service is not confirmed active")
    if host["available_mib"] < minimum_available_mib:
        warnings.append("Host MemAvailable below preliminary review threshold")
    if host["disk_free_gib"] < minimum_disk_gib:
        warnings.append("Free root filesystem space below preliminary review threshold")
    if host["swap_total_mib"] > 0 and host["swap_free_mib"] < host["swap_total_mib"] * 0.2:
        warnings.append("Swap nearly exhausted")
    if service["rss_mib"] is None:
        warnings.append("PRP JVM RSS not readable; do not infer Java memory from host total")
    return {
        "assessment": "manual_capacity_review_required",
        "safe_to_deploy": False,
        "thresholds_for_review": {
            "minimum_available_mib": minimum_available_mib,
            "minimum_disk_gib": minimum_disk_gib,
        },
        "measurements": measurement,
        "warnings": warnings,
        "not_evaluated": [
            "historical/peak traffic; single snapshot is not a stress test",
            "MySQL, Nginx, JVM heap/GC and Docker resource consumption separately",
            "TLS/OAuth provider availability, migration and release preservation",
        ],
    }


def main():
    p = argparse.ArgumentParser(description="Read-only PRP systemd/JVM capacity snapshot")
    p.add_argument("--unit", default="matrix-prp.service")
    args = p.parse_args()
    try:
        outcome = assess(snapshot(unit=args.unit))
    except (OSError, ValueError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as err:
        # No raw errors: paths, invocation strings and systemd details can be
        # sensitive on production hosts.
        print(json.dumps({"assessment": "failed_closed", "safe_to_deploy": False,
                          "reason": type(err).__name__ + ": readonly measurement unavailable"}))
        raise SystemExit(2)
    print(json.dumps(outcome, ensure_ascii=False, indent=2))
    print("READ-ONLY: no flags changed and no deployment approval inferred.")


if __name__ == "__main__":
    main()
