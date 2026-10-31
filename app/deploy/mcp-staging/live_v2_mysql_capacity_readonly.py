#!/usr/bin/env python3
"""Bounded, source-pinned, READ-ONLY capacity inventory for live V2 MySQL.

Only inspect the exact existing V2 MySQL container and measure its Docker
named volume's aggregate filesystem footprint. No MySQL login, SQL, Docker
exec/cp, backup, container changes, environment, credentials or user rows.
This is NOT a backup, restore, safe I/O budget, migration or release permit.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

CONTAINER = "prp-mcp-v2-mysql-1"
PROJECT = "prp-mcp-v2"
MYSQL_DEST = "/var/lib/mysql"
IMAGE = "mysql:8.4"
MIB = 1024 * 1024
GIB = 1024 * MIB
MIN_MEMORY = 2 * GIB
BASE_RESERVE = 4 * GIB
DU_TIMEOUT = 30
DOCKER_TIMEOUT = 8


class InventoryError(Exception):
    pass


def cmd(args, *, runner=subprocess.run, timeout=DOCKER_TIMEOUT):
    try:
        result = runner(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                        check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InventoryError("READ_ONLY_HOST_COMMAND_UNAVAILABLE") from exc
    if result.returncode != 0 or len(result.stdout) > 65536:
        raise InventoryError("READ_ONLY_HOST_COMMAND_FAILED")
    try:
        return result.stdout.decode("utf-8").strip()
    except UnicodeError as exc:
        raise InventoryError("HOST_METADATA_ENCODING_INVALID") from exc


def checked_v2_mount(mounts):
    if not isinstance(mounts, list):
        raise InventoryError("MOUNT_METADATA_INVALID")
    found = [m for m in mounts if isinstance(m, dict)
             and m.get("Destination") == MYSQL_DEST]
    if len(found) != 1:
        raise InventoryError("V2_MYSQL_MOUNT_NOT_UNIQUE")
    mount = found[0]
    if mount.get("Type") != "volume":
        raise InventoryError("V2_MYSQL_NAMED_VOLUME_REQUIRED")
    name = mount.get("Name")
    source = mount.get("Source")
    if (not isinstance(name, str) or
            not re.fullmatch(r"prp-mcp-v2[_-][A-Za-z0-9_-]{1,100}", name) or
            not isinstance(source, str) or not source.startswith("/")):
        raise InventoryError("V2_VOLUME_IDENTITY_UNVERIFIED")
    path = Path(source)
    # Accommodate a custom Docker data root, but never a broad or symlinked
    # path. An actual named volume must end in /volumes/<name>/_data.
    if (len(path.parts) < 5 or
            path.parts[-3:] != ("volumes", name, "_data") or
            not path.is_dir() or path.is_symlink() or
            str(path.resolve()) != str(path)):
        raise InventoryError("V2_VOLUME_SOURCE_UNSAFE")
    return path


def mem_available():
    try:
        raw = Path("/proc/meminfo").read_text(encoding="ascii")
        found = re.search(r"^MemAvailable:\s+([0-9]+) kB$", raw, re.M)
        if not found:
            raise InventoryError("AVAILABLE_MEMORY_UNVERIFIED")
        return int(found.group(1)) * 1024
    except (OSError, UnicodeError) as exc:
        raise InventoryError("AVAILABLE_MEMORY_UNVERIFIED") from exc


def disk_footprint_mib(path, runner=subprocess.run):
    result = cmd(["nice", "-n", "15", "ionice", "-c3",
                  "du", "-sk", "-x", "--", str(path)],
                 runner=runner, timeout=DU_TIMEOUT)
    hit = re.fullmatch(r"([0-9]+)\t[^\n]+", result)
    if not hit or int(hit.group(1)) < 1:
        raise InventoryError("V2_DATA_FOOTPRINT_UNVERIFIED")
    return (int(hit.group(1)) * 1024 + MIB - 1) // MIB


def verdict(*, image, state, project, mem_bytes, free_bytes,
            footprint_mib, same_root_device):
    required_mib = 3 * footprint_mib + BASE_RESERVE // MIB
    valid = state == "running" and project == PROJECT and image == IMAGE
    decision = "BLOCKED_OR_UNVERIFIED"
    if valid and mem_bytes >= MIN_MEMORY:
        if free_bytes < required_mib * MIB:
            decision = "CAPACITY_HEURISTIC_INSUFFICIENT"
        else:
            decision = "RESOURCE_ENVELOPE_REVIEW_ONLY"
    return {
        "purpose": "LIVE_V2_MYSQL_CAPACITY_READ_ONLY",
        "v2_mysql_running": state == "running",
        "v2_compose_project_verified": project == PROJECT,
        "v2_mysql_image_verified": image == IMAGE,
        "v2_named_data_volume_verified": True,
        "data_footprint_mib": footprint_mib,
        "host_available_memory_mib": mem_bytes // MIB,
        "v2_data_fs_free_mib": free_bytes // MIB,
        "same_filesystem_as_host_root": same_root_device,
        "initial_heuristic_requirement_mib": required_mib,
        "capacity_decision": decision,
        "point_in_time_only": True,
        "real_backup_performed": False,
        "restore_executed": False,
        "database_modified": False,
        "container_modified": False,
        "g0_b2_approval_issued": False,
        "deployment_permitted": False,
    }


def inspect(runner=subprocess.run):
    basic = {
        "purpose": "LIVE_V2_MYSQL_CAPACITY_READ_ONLY",
        "capacity_decision": "BLOCKED_OR_UNVERIFIED",
        "real_backup_performed": False,
        "restore_executed": False,
        "database_modified": False,
        "container_modified": False,
        "g0_b2_approval_issued": False,
        "deployment_permitted": False,
    }
    try:
        def docker_format(fmt):
            return cmd(["docker", "inspect", "--format", fmt, CONTAINER],
                       runner=runner)
        state = docker_format("{{.State.Status}}")
        image = docker_format("{{.Config.Image}}")
        project = docker_format('{{index .Config.Labels "com.docker.compose.project"}}')
        if (state != "running" or image != IMAGE or project != PROJECT):
            raise InventoryError("V2_CONTAINER_IDENTITY_OR_STATE_INVALID")
        mounts = json.loads(docker_format("{{json .Mounts}}"))
        source = checked_v2_mount(mounts)
        footprint = disk_footprint_mib(source, runner=runner)
        return verdict(
            state=state, image=image, project=project,
            mem_bytes=mem_available(),
            free_bytes=shutil.disk_usage(source).free,
            footprint_mib=footprint,
            same_root_device=os.stat(source).st_dev == os.stat("/").st_dev,
        )
    except (InventoryError, OSError, ValueError, TypeError,
            json.JSONDecodeError) as exc:
        basic["safe_diagnostic"] = (
            str(exc) if isinstance(exc, InventoryError)
            else "HOST_METADATA_UNAVAILABLE")
        return basic


if __name__ == "__main__":
    if len(sys.argv) != 1:
        print("NO_OPERATOR_PARAMETERS_ACCEPTED", file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(inspect(), sort_keys=True))
