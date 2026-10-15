#!/usr/bin/env python3
"""Render an intentionally restricted PRP deployment diagnostic for GitHub Actions.

Inputs are untrusted SSH stdout. Never write their raw contents to GitHub logs,
Actions summaries or artifacts. This remains useful without the optional host
"diagnose" command: it can summarize the existing read-only "status" command.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

MAX_INPUT = 8 * 1024
CODES = {
    "PRESERVED_ROW_CHANGED", "PRESERVED_FOOD_CHANGED",
    "PRESERVED_VIDEO_CHANGED", "PRESERVATION_ASSERTION",
    "MIGRATION_FAILED", "DEPLOY_COMMAND_FAILED", "DEPLOY_ERROR_UNKNOWN",
    "STALE_DIAGNOSTIC", "DIAGNOSTIC_UNAVAILABLE", "NO_DIAGNOSTIC",
}
STAGES = {
    "preservation_check", "migration_rehearsal", "backend_deploy",
    "database_migration", "health_check", "deployment", "unknown",
}
STATES = {"available", "stale", "no_log", "unavailable"}
EXCEPTIONS = {
    "AssertionError", "ValueError", "RuntimeError", "CalledProcessError",
    "TimeoutExpired", "PermissionError", "FileNotFoundError", "OSError",
}
SERVICES = {"active", "inactive", "failed", "activating", "deactivating", "unknown"}
HEX40 = re.compile(r"[a-f0-9]{40}\Z")
IDENT = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}\Z")
TABLE = re.compile(r"prp_[a-z][a-z0-9_]{0,62}\Z")
UTC_TIMESTAMP = re.compile(r"20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ\Z")


def load_untrusted(path: Path) -> dict:
    try:
        if not path.is_file() or path.stat().st_size > MAX_INPUT:
            return {}
        parsed = json.loads(path.read_text(encoding="utf-8"))
        return parsed if isinstance(parsed, dict) else {}
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return {}


def safe_diagnostic(data: dict) -> dict:
    state = data.get("state")
    if not isinstance(state, str) or state not in STATES:
        state = "unavailable"
    code = data.get("code") if isinstance(data.get("code"), str) and data.get("code") in CODES else "DIAGNOSTIC_UNAVAILABLE"
    stage = data.get("stage") if isinstance(data.get("stage"), str) and data.get("stage") in STAGES else "unknown"
    table = data.get("table")
    if not isinstance(table, str) or not TABLE.fullmatch(table):
        table = None
    exception = data.get("exception")
    if not isinstance(exception, str) or exception not in EXCEPTIONS:
        exception = None
    timestamp = data.get("timestamp_utc")
    if not isinstance(timestamp, str) or not UTC_TIMESTAMP.fullmatch(timestamp):
        timestamp = None
    if state != "available":
        table = None
        exception = None
    return {"state": state, "code": code, "stage": stage,
            "table": table, "exception": exception, "timestamp_utc": timestamp}


def safe_status(data: dict) -> dict:
    # No arbitrary metadata fields or user data can reach output.
    release = data.get("release")
    schema = data.get("schema_version")
    service = data.get("service")
    commit = data.get("metadata", {}).get("commit") if isinstance(data.get("metadata"), dict) else None
    return {
        "release": release if isinstance(release, str) and IDENT.fullmatch(release) else None,
        "schema_version": schema if type(schema) is int and 0 <= schema <= 999 else None,
        "service": service if isinstance(service, str) and service in SERVICES else None,
        "commit": commit if isinstance(commit, str) and HEX40.fullmatch(commit) else None,
    }


def create_report(diagnostic: dict, status: dict, target_sha: str) -> dict:
    return {
        "schema_version": 1,
        "outcome": "deploy_failed",
        "target_commit": target_sha if HEX40.fullmatch(target_sha) else None,
        "diagnostic": safe_diagnostic(diagnostic),
        "production": safe_status(status),
        "limitations": ("No detailed host diagnosis available until administrator-approved "
                        "read-only diagnose command is installed."
                        if not isinstance(diagnostic.get("state"), str) or diagnostic.get("state") not in STATES else None),
    }


def summary_lines(report: dict) -> list[str]:
    d, p = report["diagnostic"], report["production"]
    def display(value) -> str:
        return str(value) if value is not None else "unavailable"

    return [
        "## PRP production deployment diagnosis (sanitized)",
        "",
        "> Deployment failed; this report is not evidence of a successful release.",
        "",
        f"- Diagnostic: `{d['code']}` ({d['state']})",
        f"- Stage: `{d['stage']}`",
        f"- Object: `{display(d['table'])}`",
        f"- Exception class: `{display(d['exception'])}`",
        f"- Diagnostic timestamp (UTC): `{display(d['timestamp_utc'])}`",
        f"- Target commit: `{display(report['target_commit'])}`",
        f"- Reported production release: `{display(p['release'])}`",
        f"- Reported production commit: `{display(p['commit'])}`",
        f"- Reported schema version: `{display(p['schema_version'])}`",
        f"- Reported service status: `{display(p['service'])}`",
        "",
        "Raw tracebacks, private row identifiers, SQL, credentials, and application logs are intentionally omitted.",
        "If diagnostic is unavailable, the fixed read-only server command requires one-time administrator approval.",
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnostic", required=True, type=Path)
    parser.add_argument("--status", required=True, type=Path)
    parser.add_argument("--target-sha", required=True)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--json-output", required=True, type=Path)
    args = parser.parse_args()
    report = create_report(load_untrusted(args.diagnostic),
                           load_untrusted(args.status), args.target_sha)
    args.summary.open("a", encoding="utf-8").write("\n".join(summary_lines(report)) + "\n")
    args.json_output.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n",
                                encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
