#!/usr/bin/env python3
"""Read-only production PRP MySQL backup/clone *capacity* inventory.

Fixed container and backup directory. No MySQL login, Docker exec/cp,
Docker environment inspection, data export, network or service mutation.
Runs low-priority, bounded 'du' on a verified Docker MySQL data mount:
directory metadata only, no user/task table reads. Outputs aggregate
sizes/status only, never paths, container mounts or secrets.

This is a resource estimate, NOT consistency, a snapshot, a tested
restore, backup permission, B2/G0 approval or a deployment permit.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

CONTAINER = "matrix-mysql"
SERVICE = "matrix-prp.service"
BACKUP_ROOT = Path("/root/prp-mcp-backups")
MYSQL_DEST = "/var/lib/mysql"
MIB = 1024 * 1024
GIB = 1024 * MIB
MIN_MEMORY = 2 * GIB
BASE_RESERVE = 4 * GIB
DU_TIMEOUT = 30
ALLOWED_IMAGES = re.compile(r"^(?:(?:[a-z0-9.-]+(?::[0-9]+)?/)+)?mysql:8\.[0-9]+(?:[.-][a-zA-Z0-9._-]+)?$")


class PreflightError(Exception):
    pass


def run(args, timeout=8, runner=subprocess.run):
    try:
        result = runner(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                        check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PreflightError("READ_ONLY_HOST_COMMAND_UNAVAILABLE") from exc
    if result.returncode != 0:
        raise PreflightError("READ_ONLY_HOST_COMMAND_FAILED")
    if len(result.stdout) > 32768:
        raise PreflightError("HOST_METADATA_TOO_LARGE")
    return result.stdout.decode("utf-8", errors="strict").strip()


def validate_mysql_mount(mounts):
    if not isinstance(mounts, list):
        raise PreflightError("INVALID_DOCKER_MOUNT_METADATA")
    match = [m for m in mounts if isinstance(m, dict)
             and m.get("Destination") == MYSQL_DEST]
    if len(match) != 1:
        raise PreflightError("MYSQL_DATA_MOUNT_NOT_UNIQUE")
    m = match[0]
    if m.get("Type") not in ("volume", "bind"):
        raise PreflightError("MYSQL_DATA_MOUNT_TYPE_UNREVIEWED")
    source = m.get("Source")
    if not isinstance(source, str) or not source.startswith("/"):
        raise PreflightError("MYSQL_MOUNT_SOURCE_UNKNOWN")
    p = Path(source)
    if str(p) in ("/", "/root", "/home", "/var", "/var/lib", "/var/lib/docker"):
        raise PreflightError("MYSQL_MOUNT_SOURCE_TOO_BROAD")
    if not p.is_dir() or p.is_symlink() or str(p.resolve()) != str(p):
        raise PreflightError("MYSQL_MOUNT_SOURCE_UNSAFE")
    return p


def measure_size_mib(source, runner=subprocess.run):
    if not isinstance(source, Path) or not source.is_absolute():
        raise PreflightError("UNVERIFIED_MEASUREMENT_SOURCE")
    # Fixed metadata-only du flags. No shell, no symlink dereference,
    # no traversal across filesystem devices and no DB content read.
    out = run(["nice", "-n", "15", "ionice", "-c3",
               "du", "-sk", "-x", "--", str(source)],
              timeout=DU_TIMEOUT, runner=runner)
    match = re.fullmatch(r"([0-9]+)\t[^\n]+", out)
    if not match or int(match.group(1)) < 1:
        raise PreflightError("MYSQL_DATA_FOOTPRINT_UNVERIFIED")
    return (int(match.group(1)) * 1024 + MIB - 1) // MIB


def memory_available():
    try:
        mem = Path("/proc/meminfo").read_text(encoding="ascii")
    except (OSError, UnicodeError) as exc:
        raise PreflightError("HOST_MEMORY_UNKNOWN") from exc
    hit = re.search(r"^MemAvailable:\s+([0-9]+) kB$", mem, re.M)
    if not hit:
        raise PreflightError("HOST_MEMORY_UNKNOWN")
    return int(hit.group(1)) * 1024


def backup_parent_ok(path=BACKUP_ROOT):
    # Do not create directories or widen permissions.
    if not path.is_dir() or path.is_symlink() or str(path.resolve()) != str(path):
        return False
    stat = path.stat()
    return stat.st_uid == 0 and (stat.st_mode & 0o077) == 0


def analyze(*, active, container_status, image, mounts, backup_parent,
            free_backup_bytes, free_source_bytes, same_device, mem_bytes,
            db_size_mib):
    report = {
        "purpose": "PRODUCTION_PRP_MYSQL_CLONE_CAPACITY_READ_ONLY",
        "prp_service_active": bool(active),
        "mysql_running": container_status == "running",
        "mysql_image_allowlisted": bool(ALLOWED_IMAGES.fullmatch(image or "")),
        "data_mount_reviewed": mounts,
        "backup_parent_root_private": backup_parent,
        "data_footprint_mib": db_size_mib,
        "mem_available_mib": mem_bytes // MIB,
        "backup_fs_available_mib": free_backup_bytes // MIB,
        "data_fs_available_mib": free_source_bytes // MIB,
        "same_backup_and_data_filesystem": same_device,
        "capacity_envelope": "BLOCKED_OR_UNVERIFIED",
        "real_backup_performed": False,
        "restore_executed": False,
        "database_modified": False,
        "services_restarted": False,
        "g0_b2_approval_issued": False,
        "deployment_permitted": False,
    }
    # Conservative initial estimate only. The correct value can differ
    # substantially with compression, GTIDs, binlogs, free space, clone
    # volumes, DDL and extra backup copies. Not a signed operator budget.
    estimated_requirement = 3 * db_size_mib * MIB + BASE_RESERVE
    report["conservative_same_fs_review_requirement_mib"] = (
        estimated_requirement + MIB - 1) // MIB
    if (not active or container_status != "running"
            or not report["mysql_image_allowlisted"]
            or not mounts or not backup_parent
            or mem_bytes < MIN_MEMORY):
        return report
    if not same_device:
        report["capacity_envelope"] = "SEPARATE_FILESYSTEM_REVIEW_REQUIRED"
    elif (free_backup_bytes < estimated_requirement or
          free_source_bytes < estimated_requirement):
        report["capacity_envelope"] = "INSUFFICIENT_FOR_CONSERVATIVE_SAME_FS_REVIEW"
    else:
        report["capacity_envelope"] = "CAPACITY_ESTIMATE_REVIEW_ONLY"
    return report


def check(runner=subprocess.run):
    failed = {
        "purpose": "PRODUCTION_PRP_MYSQL_CLONE_CAPACITY_READ_ONLY",
        "capacity_envelope": "BLOCKED_OR_UNVERIFIED",
        "real_backup_performed": False,
        "restore_executed": False,
        "database_modified": False,
        "services_restarted": False,
        "g0_b2_approval_issued": False,
        "deployment_permitted": False,
    }
    try:
        active = run(["systemctl", "is-active", SERVICE], runner=runner) == "active"
        status = run(["docker", "inspect", "--format", "{{.State.Status}}",
                      CONTAINER], runner=runner)
        image = run(["docker", "inspect", "--format", "{{.Config.Image}}",
                     CONTAINER], runner=runner)
        mount_json = run(["docker", "inspect", "--format", "{{json .Mounts}}",
                          CONTAINER], runner=runner)
        source = validate_mysql_mount(json.loads(mount_json))
        footprint = measure_size_mib(source, runner=runner)
        free_backup = shutil.disk_usage(BACKUP_ROOT).free
        free_source = shutil.disk_usage(source).free
        return analyze(
            active=active, container_status=status, image=image,
            mounts=True, backup_parent=backup_parent_ok(),
            free_backup_bytes=free_backup, free_source_bytes=free_source,
            same_device=os.stat(BACKUP_ROOT).st_dev == os.stat(source).st_dev,
            mem_bytes=memory_available(), db_size_mib=footprint)
    except (PreflightError, OSError, ValueError, UnicodeError,
            json.JSONDecodeError) as exc:
        # Bounded non-secret error category only, never raw shell stderr,
        # Docker source path, login or mount metadata.
        failed["diagnostic"] = (str(exc) if isinstance(exc, PreflightError)
                                else type(exc).__name__)
        return failed


if __name__ == "__main__":
    if len(sys.argv) != 1:
        print("NO_OPERATOR_PARAMETERS_ACCEPTED", file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(check(), sort_keys=True))
