"""ENG-03B: strictly non-authorizing, offline expand migration evidence checks.

This file is NOT imported by the root-owned production publisher. It makes
no database/SSH/network calls and never runs SQL. All evidence is reviewer
supplied; its consistency is verified, not its provenance or approval.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

from expand_candidate import parse_candidate

MAX_CONTRACT_BYTES = 16384
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_NAME = re.compile(r"[a-z][a-z0-9_]{0,58}\Z")
_TYPE = re.compile(r"[a-z0-9(), ]{1,80}\Z")
_MYSQL = re.compile(r"8\.4\.[0-9]+(?:[-+][a-zA-Z0-9_.-]+)?\Z")
_REQUIRED_CONTRACT = {
    "schema_version", "status", "mode", "source_commit", "base_schema_version",
    "target_schema_version", "mysql_family", "table", "column", "column_type",
    "sql_sha256", "old_columns_sha256", "old_rows_sha256", "old_indexes_sha256",
    "old_constraints_sha256", "old_triggers_sha256", "rollback_strategy",
    "production_authorized", "controller_upgrade_required",
}
_REQUIRED_SNAPSHOT = {
    "table", "mysql_version", "schema_version", "source_commit", "columns",
    "row_count", "old_rows_sha256", "indexes_sha256", "constraints_sha256",
    "triggers_sha256", "added_column_nonnull_count",
}
_REQUIRED_COLUMN = {"name", "type", "nullable", "default", "extra", "ordinal"}


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def load_json(raw: bytes, *, max_bytes: int = MAX_CONTRACT_BYTES):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= max_bytes:
        raise ValueError("Evidence JSON missing or too large")
    try:
        obj = json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeError) as error:
        raise ValueError("Invalid or duplicated evidence JSON") from error
    return obj


def exact_fields(value, fields, label):
    if type(value) is not dict or set(value) != fields:
        raise ValueError("Invalid " + label + " fields")


def valid_hash(value):
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def validate_snapshot(snapshot, label):
    exact_fields(snapshot, _REQUIRED_SNAPSHOT, label)
    if not isinstance(snapshot["table"], str) or not re.fullmatch(r"prp_[a-z][a-z0-9_]{0,58}", snapshot["table"]):
        raise ValueError("Unsafe evidence table")
    if not isinstance(snapshot["mysql_version"], str) or not _MYSQL.fullmatch(snapshot["mysql_version"]):
        raise ValueError("Unsupported MySQL evidence version")
    if type(snapshot["schema_version"]) is not int or not 1 <= snapshot["schema_version"] <= 1000:
        raise ValueError("Invalid evidence schema version")
    if not isinstance(snapshot["source_commit"], str) or not _COMMIT.fullmatch(snapshot["source_commit"]):
        raise ValueError("Invalid source commit evidence")
    if type(snapshot["row_count"]) is not int or not 0 <= snapshot["row_count"] <= 1000000000:
        raise ValueError("Invalid snapshot row count")
    null_count = snapshot["added_column_nonnull_count"]
    if null_count is not None and (type(null_count) is not int or not 0 <= null_count <= snapshot["row_count"]):
        raise ValueError("Invalid added column count")
    for key in ("old_rows_sha256", "indexes_sha256", "constraints_sha256", "triggers_sha256"):
        if not valid_hash(snapshot[key]):
            raise ValueError("Invalid evidence fingerprint: " + key)
    cols = snapshot["columns"]
    if not isinstance(cols, list) or not 1 <= len(cols) <= 256:
        raise ValueError("Invalid column evidence list")
    seen = set()
    for index, column in enumerate(cols, 1):
        exact_fields(column, _REQUIRED_COLUMN, "column")
        if not isinstance(column["name"], str) or not _NAME.fullmatch(column["name"]) or column["name"] in seen:
            raise ValueError("Invalid/duplicate column identifier")
        seen.add(column["name"])
        if not isinstance(column["type"], str) or not _TYPE.fullmatch(column["type"]) or column["type"] != column["type"].lower():
            raise ValueError("Invalid canonical database type")
        if type(column["nullable"]) is not bool or type(column["ordinal"]) is not int or column["ordinal"] != index:
            raise ValueError("Invalid column metadata")
        if column["default"] is not None and (not isinstance(column["default"], str) or len(column["default"]) > 200):
            raise ValueError("Invalid column default")
        if not isinstance(column["extra"], str) or len(column["extra"]) > 100:
            raise ValueError("Invalid column extra")
    return snapshot


def create_review_contract(sql: bytes, before: dict, *, source_commit: str, target_schema_version: int) -> dict:
    """Emit a candidate bound to a previously obtained snapshot, not an approval."""
    candidate = parse_candidate(sql)
    validate_snapshot(before, "before")
    if before["added_column_nonnull_count"] is not None or candidate.column in {x["name"] for x in before["columns"]}:
        raise ValueError("Column already exists / malformed old snapshot")
    if before["table"] != candidate.table or before["source_commit"] != source_commit:
        raise ValueError("Candidate does not match table/source")
    if type(target_schema_version) is not int or target_schema_version != before["schema_version"] + 1:
        raise ValueError("Target version must be next Flyway schema version")
    return {
        "schema_version": 1, "status": "SPECIALIST_REVIEW_REQUIRED",
        "mode": "add-nullable-column-review-only", "source_commit": source_commit,
        "base_schema_version": before["schema_version"],
        "target_schema_version": target_schema_version,
        "mysql_family": "8.4", "table": candidate.table, "column": candidate.column,
        "column_type": candidate.column_type, "sql_sha256": candidate.sql_sha256,
        "old_columns_sha256": sha(canonical(before["columns"])),
        "old_rows_sha256": before["old_rows_sha256"],
        "old_indexes_sha256": before["indexes_sha256"],
        "old_constraints_sha256": before["constraints_sha256"],
        "old_triggers_sha256": before["triggers_sha256"],
        "rollback_strategy": "application-only-no-database-rollback",
        "production_authorized": False, "controller_upgrade_required": True,
    }


def verify_review_contract(contract: dict, sql: bytes, before: dict, after: dict) -> dict:
    """Fail closed for old-row/owner/index/constraint/trigger metadata drift."""
    exact_fields(contract, _REQUIRED_CONTRACT, "contract")
    candidate = parse_candidate(sql)
    validate_snapshot(before, "before")
    validate_snapshot(after, "after")
    if (contract["schema_version"] != 1 or type(contract["schema_version"]) is not int
            or contract["status"] != "SPECIALIST_REVIEW_REQUIRED"
            or contract["mode"] != "add-nullable-column-review-only"
            or contract["rollback_strategy"] != "application-only-no-database-rollback"
            or contract["production_authorized"] is not False
            or contract["controller_upgrade_required"] is not True
            or contract["mysql_family"] != "8.4"):
        raise ValueError("Unapproved candidate contract or unsafe rollback")
    expected = {
        "table": candidate.table, "column": candidate.column, "column_type": candidate.column_type,
        "sql_sha256": candidate.sql_sha256, "source_commit": before["source_commit"],
        "base_schema_version": before["schema_version"],
        "target_schema_version": before["schema_version"] + 1,
        "old_columns_sha256": sha(canonical(before["columns"])),
        "old_rows_sha256": before["old_rows_sha256"], "old_indexes_sha256": before["indexes_sha256"],
        "old_constraints_sha256": before["constraints_sha256"],
        "old_triggers_sha256": before["triggers_sha256"],
    }
    if any(type(contract[key]) is not type(value) or contract[key] != value for key, value in expected.items()):
        raise ValueError("Contract / SQL / original fingerprint mismatch")
    if any(not valid_hash(contract[key]) for key in _REQUIRED_CONTRACT if key.endswith("_sha256")):
        raise ValueError("Malformed digest")
    if (before["table"] != candidate.table or after["table"] != candidate.table
            or before["mysql_version"] != after["mysql_version"]
            or before["source_commit"] != after["source_commit"]
            or after["schema_version"] != before["schema_version"]
            or before["added_column_nonnull_count"] is not None
            or after["added_column_nonnull_count"] != 0):
        raise ValueError("Rehearsal did not preserve version, ownership scope or null expansion")
    if (before["row_count"] != after["row_count"]
            or before["old_rows_sha256"] != after["old_rows_sha256"]
            or any(before[k] != after[k] for k in
                   ("indexes_sha256", "constraints_sha256", "triggers_sha256"))):
        raise ValueError("Existing rows/ownership/indexes/constraints/triggers changed")
    old = before["columns"]
    new = after["columns"]
    if len(new) != len(old) + 1 or new[:len(old)] != old:
        raise ValueError("Original column metadata mutated or the new column was not appended")
    addition = new[-1]
    if (addition["name"] != candidate.column or
            addition["type"] != candidate.column_type.lower() or
            addition["nullable"] is not True or addition["default"] is not None or
            addition["extra"] != "" or addition["ordinal"] != len(new)):
        raise ValueError("Unexpected new column definition")
    return {
        "schema_version": 1, "classification": "READY_FOR_SPECIALIST_REVIEW",
        "production_authorized": False, "controller_upgrade_required": True,
        "table": candidate.table, "column": candidate.column, "sql_sha256": candidate.sql_sha256,
        "row_count_preserved": before["row_count"],
        "evidence_sha256": sha(canonical({"before": before, "after": after})),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline, non-authorizing expansion rehearsal evidence checker")
    for name in ("sql", "contract", "before", "after"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = verify_review_contract(
            load_json(args.contract.read_bytes()), args.sql.read_bytes(),
            load_json(args.before.read_bytes()), load_json(args.after.read_bytes()))
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(2, f"Evidence rejected: {type(error).__name__}\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
