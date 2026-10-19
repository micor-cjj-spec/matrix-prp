#!/usr/bin/python3 -I
"""Fixed, root-owned, read-only production inspector.

Intended ONLY behind the dedicated prp-inspect forced SSH command and an
exact no-argument sudoers rule. Returns whitelisted metadata, never raw logs.
It is not an SSH policy attestation and cannot authorize deployment.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

FILES = {
    "controller": "/usr/local/sbin/prp-release",
    "gateway": "/usr/local/bin/prp-deploy-gateway",
    "diagnose": "/usr/local/sbin/prp-diagnose",
}
SERVICE = "matrix-prp.service"
MAX_FILE = 8 * 1024 * 1024
MAX_OUTPUT = 128 * 1024
ENV = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}
STATES = {"active", "inactive", "failed", "activating", "deactivating", "unknown"}
SUBSTATES = {"running", "dead", "failed", "exited", "start", "stop", "auto-restart", "unknown"}
DIAG_STATES = {"available", "stale", "no_log", "unavailable"}
DIAG_CODES = {
    "PRESERVED_ROW_CHANGED", "PRESERVED_FOOD_CHANGED",
    "PRESERVED_VIDEO_CHANGED", "PRESERVATION_ASSERTION",
    "UNEXPECTED_BUSINESS_TABLE", "UNEXPECTED_MIGRATION_ROWS",
    "MIGRATION_FAILED", "DEPLOY_COMMAND_FAILED", "DEPLOY_ERROR_UNKNOWN",
    "STALE_DIAGNOSTIC", "DIAGNOSTIC_UNAVAILABLE", "NO_DIAGNOSTIC",
}
DIAG_STAGES = {
    "preservation_check", "migration_rehearsal", "backend_deploy",
    "database_migration", "health_check", "deployment", "unknown",
}
EXCEPTIONS = {
    "AssertionError", "ValueError", "RuntimeError", "CalledProcessError",
    "TimeoutExpired", "PermissionError", "FileNotFoundError", "OSError",
}
UTC = re.compile(r"20\d{2}-\d\d-\d\dT\d\d:\d\d:\d\dZ\Z")


def fixed_command(args: list[str], *, seconds: int = 6) -> bytes | None:
    """Absolute executable + literal arguments; never shell, env or user input."""
    try:
        result = subprocess.run(args, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                env=ENV, timeout=seconds, check=False)
        if result.returncode != 0 or len(result.stdout) > MAX_OUTPUT:
            return None
        return result.stdout
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def approved_file_digest(path: str) -> dict:
    """Never follow symlinks or emit contents, ownership names, or file paths."""
    unavailable = {"trusted_file": False, "sha256": None}
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        with os.fdopen(os.open(path, flags), "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or
                    info.st_mode & 0o022 or info.st_nlink != 1 or
                    not 0 < info.st_size <= MAX_FILE):
                return unavailable
            digest = hashlib.sha256()
            while block := stream.read(65536):
                digest.update(block)
            return {"trusted_file": True, "sha256": digest.hexdigest()}
    except (OSError, ValueError):
        return unavailable


def service_report() -> dict:
    result = {
        "active_state": "unknown", "sub_state": "unknown",
        "exit_status": None, "restart_count": None,
    }
    raw = fixed_command([
        "/usr/bin/systemctl", "show", SERVICE, "--no-pager",
        "--property=ActiveState", "--property=SubState",
        "--property=ExecMainStatus", "--property=NRestarts",
    ])
    if raw is None:
        return result
    try:
        parsed = dict(line.split("=", 1) for line in raw.decode("utf-8").splitlines()
                      if line.count("=") == 1)
        active = parsed.get("ActiveState", "unknown")
        sub = parsed.get("SubState", "unknown")
        result["active_state"] = active if active in STATES else "unknown"
        result["sub_state"] = sub if sub in SUBSTATES else "unknown"
        for key, field, maximum in [
            ("ExecMainStatus", "exit_status", 255),
            ("NRestarts", "restart_count", 100000),
        ]:
            value = parsed.get(key, "")
            if re.fullmatch(r"\d{1,6}", value) and int(value) <= maximum:
                result[field] = int(value)
    except (UnicodeError, ValueError):
        pass
    return result


def deployment_diagnostic() -> dict:
    empty = {
        "state": "unavailable", "code": "DIAGNOSTIC_UNAVAILABLE",
        "stage": "unknown", "exception": None, "timestamp_utc": None,
    }
    raw = fixed_command(["/usr/local/sbin/prp-diagnose"])
    if raw is None or len(raw) > 8192:
        return empty
    try:
        obj = json.loads(raw)
        if (not isinstance(obj, dict) or
                set(obj) != {"schema_version", "state", "code", "stage",
                             "table", "exception", "timestamp_utc"} or
                type(obj["schema_version"]) is not int or obj["schema_version"] != 1):
            return empty
        state, code, stage = obj["state"], obj["code"], obj["stage"]
        if state not in DIAG_STATES or code not in DIAG_CODES or stage not in DIAG_STAGES:
            return empty
        exception = obj["exception"] if obj["exception"] in EXCEPTIONS else None
        stamp = obj["timestamp_utc"]
        if not isinstance(stamp, str) or not UTC.fullmatch(stamp):
            stamp = None
        if state != "available":
            exception = None
            stamp = None
        return {"state": state, "code": code, "stage": stage,
                "exception": exception, "timestamp_utc": stamp}
    except (ValueError, TypeError, RecursionError, UnicodeError):
        return empty


def journal_counts() -> dict:
    unavailable = {
        "state": "unavailable", "scanned_lines": 0, "error_lines": 0,
        "timeout_lines": 0, "database_lines": 0, "oom_lines": 0,
    }
    raw = fixed_command([
        "/usr/bin/journalctl", "--unit=" + SERVICE, "--since=-10 minutes",
        "--lines=100", "--no-pager", "--output=cat",
    ])
    if raw is None:
        return unavailable
    # Private log text is processed only in memory. NEVER print the lines.
    lines = raw.decode("utf-8", errors="replace").splitlines()[:100]
    return {
        "state": "available",
        "scanned_lines": len(lines),
        "error_lines": sum(bool(re.search(r"(?i)\b(?:ERROR|FATAL|Exception)\b", s)) for s in lines),
        "timeout_lines": sum(bool(re.search(r"(?i)\btimeout\b|timed out", s)) for s in lines),
        "database_lines": sum(bool(re.search(r"(?i)\b(?:SQL|JDBC|Flyway)\b", s)) for s in lines),
        "oom_lines": sum("OutOfMemoryError" in s for s in lines),
    }


def report() -> dict:
    return {
        "schema_version": 1,
        "observed_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "service": service_report(),
        "components": {key: approved_file_digest(value) for key, value in FILES.items()},
        "deployment_diagnostic": deployment_diagnostic(),
        "journal": journal_counts(),
    }


def main() -> int:
    if len(sys.argv) != 1 or os.geteuid() != 0:
        return 2
    try:
        output = report()
    except Exception:
        # No raw exception text, paths or log contents go to the SSH caller.
        return 1
    print(json.dumps(output, separators=(",", ":"), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
