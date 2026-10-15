#!/usr/bin/env python3
"""Root-only, fixed-path deployment failure classifier.

This is NOT a raw log reader. It emits a fixed-schema, secret-free report.
The approved forced SSH gateway may expose it as the literal "diagnose"
command after independent administrator review and installation.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys

LOG_PATH = Path("/var/lib/matrix-prp-deploy/last-error.log")
MAX_BYTES = 64 * 1024
MAX_AGE_SECONDS = 2 * 3600
TABLE = re.compile(r"\b(prp_[a-z][a-z0-9_]{0,62})\b")
HISTORICAL_ROW = re.compile(
    r"Historical row changed or deleted['\"],\s*['\"](prp_[a-z][a-z0-9_]{0,62})['\"]"
)
APPROVED_STAGES = (
    ("assert_preserved", "preservation_check"),
    ("rehearse", "migration_rehearsal"),
    ("deploy_backend", "backend_deploy"),
    ("migrate", "database_migration"),
    ("check", "health_check"),
    ("deploy", "deployment"),
)
SAFE_ERRORS = {
    "AssertionError", "ValueError", "RuntimeError", "CalledProcessError",
    "TimeoutExpired", "PermissionError", "FileNotFoundError", "OSError",
}


def classify(trace: str) -> dict[str, str | None]:
    # Never return traceback lines, SQL, rows, primary keys or free text.
    result: dict[str, str | None] = {
        "code": "DEPLOY_ERROR_UNKNOWN",
        "stage": "unknown",
        "table": None,
        "exception": None,
    }
    for function, stage in APPROVED_STAGES:
        if re.search(r"\bin " + re.escape(function) + r"\s*(?:\n|$)", trace):
            result["stage"] = stage
            break

    found = re.findall(r"(?m)^(?:[\w.]*\.)?(\w+):", trace)
    if found and found[-1] in SAFE_ERRORS:
        result["exception"] = found[-1]

    match = HISTORICAL_ROW.search(trace)
    if match:
        result.update(code="PRESERVED_ROW_CHANGED", stage="preservation_check", table=match.group(1))
    elif "Existing food row changed or deleted" in trace:
        result.update(code="PRESERVED_FOOD_CHANGED", stage="preservation_check")
    elif "Video ownership or records changed" in trace:
        result.update(code="PRESERVED_VIDEO_CHANGED", stage="preservation_check")
    elif "assert_preserved" in trace and "AssertionError" in trace:
        result.update(code="PRESERVATION_ASSERTION", stage="preservation_check")
    elif "Flyway" in trace or "Migration failed" in trace:
        result.update(code="MIGRATION_FAILED", stage="database_migration")
    elif "CalledProcessError" in trace:
        result["code"] = "DEPLOY_COMMAND_FAILED"
    return result


def report(path: Path = LOG_PATH, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    base = {
        "schema_version": 1,
        "state": "no_log",
        "code": "NO_DIAGNOSTIC",
        "stage": "unknown",
        "table": None,
        "exception": None,
        "timestamp_utc": None,
    }
    try:
        st = path.stat()
        if not path.is_file() or st.st_size == 0:
            return base
        # Do not disclose old failures as the reason for a new run.
        age = now.timestamp() - st.st_mtime
        if age < -300 or age > MAX_AGE_SECONDS:
            return {**base, "state": "stale", "code": "STALE_DIAGNOSTIC"}
        with path.open("rb") as file:
            file.seek(max(0, st.st_size - MAX_BYTES))
            raw = file.read(MAX_BYTES).decode("utf-8", errors="replace")
        utc = datetime.fromtimestamp(st.st_mtime, timezone.utc).replace(microsecond=0)
        return {
            **base,
            **classify(raw),
            "state": "available",
            "timestamp_utc": utc.isoformat().replace("+00:00", "Z"),
        }
    except FileNotFoundError:
        return base
    except (OSError, ValueError, OverflowError):
        return {**base, "state": "unavailable", "code": "DIAGNOSTIC_UNAVAILABLE"}


def main() -> int:
    if len(sys.argv) != 1 or os.geteuid() != 0:
        return 2
    # Only allowlist fields can reach stdout. Never print caught exceptions.
    print(json.dumps(report(), ensure_ascii=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
