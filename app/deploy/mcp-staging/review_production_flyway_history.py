#!/usr/bin/env python3
"""Offline reviewer for sanitized PRP Flyway metadata, NOT a DB client.

Never connects to MySQL, accepts credentials or changes a database.
Even a match is REVIEW_ONLY and cannot grant G0/B2 or deploy approval.
"""
import argparse
import json
from pathlib import Path
import re
import sys

SCHEMA_DEFAULT = "matrix_prp"
MIGRATIONS = Path(__file__).resolve().parents[2] / "backend/src/main/resources/db/migration"
MIGRATION_PATTERN = re.compile(r"^V([1-9][0-9]*)__([a-zA-Z0-9_]+)\.sql$")
KEYS = {"installed_rank", "version", "script", "checksum", "success"}
MAX_BYTES = 32 * 1024


def source_scripts(folder=MIGRATIONS):
    expected = {}
    for path in folder.iterdir():
        if not path.is_file():
            continue
        match = MIGRATION_PATTERN.fullmatch(path.name)
        if match:
            version = int(match.group(1))
            if version in expected:
                raise ValueError("DUPLICATE_CANDIDATE_MIGRATION_VERSION")
            expected[version] = path.name
    if set(expected) != set(range(1, 29)):
        raise ValueError("CANDIDATE_EXPECTED_MIGRATION_RANGE_NOT_1_TO_28")
    return expected


def analyze(data, scripts, expected_schema=SCHEMA_DEFAULT):
    # Deliberately validate exact operator report format; no untrusted
    # filenames, values, SQL text or raw rows appear in output.
    fail = lambda reason: {
        "decision": "BLOCKED_OR_UNVERIFIED",
        "reason": reason,
        "history_rows_checked": 0,
        "source_migration_names_match": False,
        "flyway_checksums_verified": False,
        "deployment_permitted": False,
        "g0_b2_authorization": "NOT_ESTABLISHED",
    }
    if (not isinstance(data, dict)
            or set(data) != {"schema", "history"}
            or data.get("schema") != expected_schema):
        return fail("SCHEMA_UNVERIFIED_OR_REPORT_FORMAT_INVALID")
    rows = data.get("history")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 64:
        return fail("MISSING_OR_UNEXPECTED_HISTORY_ROWS")
    versions = []
    ranks = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != KEYS:
            return fail("HISTORY_ROW_SHAPE_INVALID")
        ver = row["version"]
        rank = row["installed_rank"]
        checksum = row["checksum"]
        if (not isinstance(ver, str) or not re.fullmatch(r"[1-9][0-9]*", ver)
                or type(rank) is not int or not 1 <= rank <= 9999
                or type(checksum) is not int or not -(2**31) <= checksum < 2**31
                or row["success"] != "PASS"):
            return fail("HISTORY_ROW_INVALID_FAILED_OR_BASELINED")
        num = int(ver)
        if (num not in scripts or row["script"] != scripts[num]):
            return fail("MIGRATION_VERSION_OR_SCRIPT_DRIFT")
        versions.append(num)
        ranks.append(rank)
    if len(set(versions)) != len(versions) or len(set(ranks)) != len(ranks):
        return fail("DUPLICATE_MIGRATION_OR_INSTALL_RANK")
    # MySQL JSON_ARRAYAGG does not guarantee array element order.
    # Sort by the trusted installed_rank *value* before comparing order.
    ordered = sorted(zip(ranks, versions))
    ordered_ranks = [rank for rank, _ in ordered]
    ordered_versions = [version for _, version in ordered]
    if ordered_ranks != list(range(1, len(ranks) + 1)):
        return fail("HISTORY_INSTALL_RANK_GAP_OR_BASELINE")
    if ordered_versions != sorted(ordered_versions):
        return fail("HISTORY_NOT_IN_ASCENDING_INSTALL_ORDER")
    latest = max(versions)
    if latest not in (24, 28) or ordered_versions != list(range(1, latest + 1)):
        return fail("PARTIAL_OR_UNEXPECTED_MIGRATION_CHAIN")
    return {
        "decision": ("V24_SOURCE_HISTORY_SHAPE_MATCH_CHECKSUMS_UNVERIFIED"
                     if latest == 24 else
                     "V28_SOURCE_HISTORY_SHAPE_MATCH_CHECKSUMS_UNVERIFIED"),
        "reason": "REQUIRES_INDEPENDENT_FLYWAY_CHECKSUM_VALIDATION_AND_RESTORED_COPY",
        "history_rows_checked": len(rows),
        "source_migration_names_match": True,
        "flyway_checksums_verified": False,
        "deployment_permitted": False,
        "g0_b2_authorization": "NOT_ESTABLISHED",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path,
                        help="Local metadata-only JSON from independently approved read-only SQL")
    parser.add_argument("--expected-schema", default=SCHEMA_DEFAULT)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", args.expected_schema):
        parser.error("Expected schema must be an ordinary DB name")
    try:
        path = args.input
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
            raise ValueError("REPORT_FILE_NOT_REGULAR_OR_TOO_LARGE")
        data = json.loads(path.read_text(encoding="utf-8"))
        result = analyze(data, source_scripts(), args.expected_schema)
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError):
        result = {
            "decision": "BLOCKED_OR_UNVERIFIED",
            "reason": "HISTORY_REPORT_OR_SOURCE_UNAVAILABLE",
            "flyway_checksums_verified": False,
            "deployment_permitted": False,
            "g0_b2_authorization": "NOT_ESTABLISHED",
        }
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return 0 if result["decision"].startswith(("V24_", "V28_")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
