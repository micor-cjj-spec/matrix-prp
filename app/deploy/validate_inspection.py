#!/usr/bin/env python3
"""Treat all production SSH stdout as untrusted; publish only validated fields."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from prp_readonly_report import (STATES, SUBSTATES, DIAG_STATES,
                                DIAG_CODES, DIAG_STAGES, EXCEPTIONS)

DIGEST = re.compile(r"[0-9a-f]{64}\Z")
STAMP = re.compile(r"20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ\Z")
COMPONENTS = {"controller", "gateway", "diagnose"}
COUNTERS = {"scanned_lines", "error_lines", "timeout_lines", "database_lines", "oom_lines"}


def strict_obj(obj, fields):
    if not isinstance(obj, dict) or set(obj) != fields:
        raise ValueError("INVALID_REPORT")


def validate(obj):
    strict_obj(obj, {"schema_version", "observed_utc", "service",
                     "components", "deployment_diagnostic", "journal"})
    if type(obj["schema_version"]) is not int or obj["schema_version"] != 1:
        raise ValueError("INVALID_REPORT")
    stamp = obj["observed_utc"]
    if not isinstance(stamp, str) or not STAMP.fullmatch(stamp):
        raise ValueError("INVALID_REPORT")
    now = datetime.now(timezone.utc)
    age = (now - datetime.fromisoformat(stamp.replace("Z", "+00:00"))).total_seconds()
    if not -300 <= age <= 600:
        raise ValueError("STALE_REPORT")

    service = obj["service"]
    strict_obj(service, {"active_state", "sub_state", "exit_status", "restart_count"})
    if service["active_state"] not in STATES or service["sub_state"] not in SUBSTATES:
        raise ValueError("INVALID_REPORT")
    for field, cap in [("exit_status", 255), ("restart_count", 100000)]:
        value = service[field]
        if value is not None and (type(value) is not int or not 0 <= value <= cap):
            raise ValueError("INVALID_REPORT")

    parts = obj["components"]
    strict_obj(parts, COMPONENTS)
    for item in parts.values():
        strict_obj(item, {"trusted_file", "sha256"})
        if type(item["trusted_file"]) is not bool:
            raise ValueError("INVALID_REPORT")
        digest = item["sha256"]
        if item["trusted_file"]:
            if not isinstance(digest, str) or not DIGEST.fullmatch(digest):
                raise ValueError("INVALID_REPORT")
        elif digest is not None:
            raise ValueError("INVALID_REPORT")

    diag = obj["deployment_diagnostic"]
    strict_obj(diag, {"state", "code", "stage", "exception", "timestamp_utc"})
    if diag["state"] not in DIAG_STATES or diag["code"] not in DIAG_CODES or diag["stage"] not in DIAG_STAGES:
        raise ValueError("INVALID_REPORT")
    if diag["exception"] is not None and diag["exception"] not in EXCEPTIONS:
        raise ValueError("INVALID_REPORT")
    if diag["timestamp_utc"] is not None and (
            not isinstance(diag["timestamp_utc"], str) or
            not STAMP.fullmatch(diag["timestamp_utc"])):
        raise ValueError("INVALID_REPORT")

    journal = obj["journal"]
    strict_obj(journal, {"state"} | COUNTERS)
    if journal["state"] not in {"available", "unavailable"}:
        raise ValueError("INVALID_REPORT")
    for field in COUNTERS:
        value = journal[field]
        if type(value) is not int or not 0 <= value <= 100:
            raise ValueError("INVALID_REPORT")
    if any(journal[k] > journal["scanned_lines"] for k in COUNTERS - {"scanned_lines"}):
        raise ValueError("INVALID_REPORT")
    return obj


def safe_failure(code):
    return {"schema_version": 1, "status": "unavailable", "code": code,
            "production_gate_passed": False}


def output_report(obj, manifest):
    approved = manifest["approved_controller"]["sha256"]
    policy = manifest["approved_ssh_policy"]
    expected = {"controller": approved, "gateway": policy["gateway_sha256"],
                "diagnose": policy["attestor_sha256"]}
    status = {}
    for name in sorted(COMPONENTS):
        observed = obj["components"][name]["sha256"]
        status[name] = "unavailable" if observed is None else (
            "match" if observed == expected[name] else "mismatch")
    # Does NOT imply a loaded SSH policy proof or production deploy authorization.
    return {
        "schema_version": 1,
        "status": "report_available",
        "production_gate_passed": False,
        "observed_utc": obj["observed_utc"],
        "service": obj["service"],
        "approved_file_matches": status,
        "deployment_diagnostic": obj["deployment_diagnostic"],
        "journal": obj["journal"],
        "limitation": "Read-only file checks are NOT a live SSH-policy proof.",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--summary", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    a = p.parse_args()
    final = safe_failure("INSPECT_UNAVAILABLE")
    try:
        if not a.input.is_file() or not 0 < a.input.stat().st_size <= 8192:
            raise ValueError("INVALID_REPORT")
        obj = validate(json.loads(a.input.read_text(encoding="utf-8")))
        manifest = json.loads(a.manifest.read_text(encoding="utf-8"))
        final = output_report(obj, manifest)
    except (OSError, ValueError, UnicodeError, KeyError, TypeError, RecursionError):
        final = safe_failure("INSPECT_INVALID_OR_UNAVAILABLE")
    a.output.write_text(json.dumps(final, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    summary = [
        "## PRP independent read-only inspection",
        "",
        "This report is advisory; it cannot authorize deployment, restart, migrate, or change SSH policy.",
        "",
    ]
    if final["status"] == "report_available":
        summary.extend([
            "- Inspection status: report received and strictly validated",
            "- Service: `" + final["service"]["active_state"] + "`",
            "- Installed controller hash: `" + final["approved_file_matches"]["controller"] + "`",
            "- Installed gateway hash: `" + final["approved_file_matches"]["gateway"] + "`",
            "- Installed diagnose hash: `" + final["approved_file_matches"]["diagnose"] + "`",
            "- Deployment diagnostic: `" + final["deployment_diagnostic"]["code"] + "`",
            "- Recent service error lines (bounded): `" + str(final["journal"]["error_lines"]) + "`",
        ])
    else:
        summary.append("- Inspection unavailable: SSH authentication, server bootstrap, or report validation may be incomplete.")
    summary.append("")
    summary.append("No raw logs, credentials, configuration contents, user data or SSH stdout are published.")
    a.summary.open("a", encoding="utf-8").write("\n".join(summary) + "\n")
    return 0 if final["status"] == "report_available" else 1


if __name__ == "__main__":
    raise SystemExit(main())
