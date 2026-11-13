#!/usr/bin/env python3
"""Verify migration bytes in an unstarted, disposable OCI runtime JAR.

No production network, SQL, credentials, signing or releases. This only
asserts the candidate JAR contains the exact source checkout migrations,
not that the production host runs this JAR or has matching history.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from zipfile import BadZipFile, ZipFile

SQL = re.compile(r"^V([1-9][0-9]*)__([a-zA-Z0-9_]+)\.sql$")
PREFIX = "BOOT-INF/classes/db/migration/"
EXPECTED_VERSIONS = set(range(1, 30))
FUTURE_POLICY = Path(__file__).resolve().parents[1] / "migration-policy.json"
MAX_SQL_BYTES = 1024 * 1024
MAX_ZIP_ENTRIES = 50000
MAX_JAR_BYTES = 240 * 1024 * 1024


def validate(jar: Path, source: Path, future_policy: Path | None = None) -> dict:
    def blocked(reason: str) -> dict:
        return {
            "decision": "BLOCKED",
            "reason": reason,
            "source_migrations": 0,
            "jar_migrations": 0,
            "identical_raw_bytes": False,
            "deployment_permitted": False,
        }

    if (jar.is_symlink() or source.is_symlink() or
            not jar.is_file() or not source.is_dir() or
            not 0 < jar.stat().st_size <= MAX_JAR_BYTES):
        return blocked("INPUT_NOT_TRUSTED_REGULAR_CI_ARTIFACT")
    local: dict[str, bytes] = {}
    for item in source.iterdir():
        if item.name.endswith(".sql") and not SQL.fullmatch(item.name):
            return blocked("UNRECOGNIZED_SOURCE_SQL_FILENAME")
        if SQL.fullmatch(item.name):
            if item.is_symlink() or not item.is_file() or item.stat().st_size > MAX_SQL_BYTES:
                return blocked("SOURCE_SQL_NOT_TRUSTED_REGULAR_FILE")
            local[item.name] = item.read_bytes()
    versions = [int(SQL.fullmatch(name).group(1)) for name in local]
    historic = [v for v in versions if v <= 29]
    future = [v for v in versions if v > 29]
    if set(historic) != EXPECTED_VERSIONS or len(historic) != len(EXPECTED_VERSIONS):
        return blocked("SOURCE_EXPECTED_V1_V29_INCOMPLETE")
    if future:
        latest = max(future)
        if sorted(future) != list(range(30, latest + 1)):
            return blocked("FUTURE_MIGRATIONS_NOT_CONTIGUOUS")
        contract = future_policy if future_policy is not None else FUTURE_POLICY
        if contract.is_symlink() or not contract.is_file() or contract.stat().st_size > MAX_SQL_BYTES:
            return blocked("FUTURE_MIGRATION_POLICY_UNTRUSTED")
        policy = json.loads(contract.read_text(encoding="utf-8"))
        if policy.get("schema_version") != 1 or not isinstance(policy.get("rules"),list):
            return blocked("FUTURE_MIGRATION_POLICY_INVALID")
        rules = [r for r in policy["rules"] if isinstance(r,dict)
                 and type(r.get("version")) is int and r["version"] > 29]
        by_version = {r["version"]: r for r in rules}
        if len(by_version) != len(rules) or set(by_version) != set(future):
            return blocked("FUTURE_MIGRATION_POLICY_MISSING_OR_DUPLICATE")
        for name, raw in local.items():
            match = SQL.fullmatch(name)
            version = int(match.group(1))
            if version <= 29:
                continue
            rule=by_version[version]
            if (rule.get("file") != name or rule.get("mode") != "create-empty"
                or not isinstance(rule.get("tables"),list) or not rule["tables"]):
                return blocked("FUTURE_MIGRATION_NOT_CREATE_EMPTY")
            if hashlib.sha256(raw).hexdigest() != rule.get("sha256"):
                return blocked("FUTURE_MIGRATION_POLICY_DIGEST_DRIFT")

    with ZipFile(jar) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_ZIP_ENTRIES:
            return blocked("UNBOUNDED_ZIP_ENTRIES")
        names = [e.filename for e in entries]
        if len(set(names)) != len(names):
            return blocked("DUPLICATED_ZIP_ENTRY_NAMES")
        packaged: dict[str, bytes] = {}
        for info in entries:
            name = info.filename
            if not name.startswith(PREFIX):
                continue
            leaf = name[len(PREFIX):]
            if not leaf or name.endswith("/"):
                continue
            if "/" in leaf or not SQL.fullmatch(leaf) or info.file_size > MAX_SQL_BYTES:
                return blocked("UNRECOGNIZED_PACKAGED_MIGRATION_FILE")
            packaged[leaf] = archive.read(info)
        if set(packaged) != set(local):
            return blocked("JAR_MIGRATION_FILE_SET_DRIFT")
        if any(packaged[name] != raw for name, raw in local.items()):
            return blocked("JAR_MIGRATION_BYTES_DRIFT")
        return {
            "decision": "CANDIDATE_JAR_SOURCE_MIGRATIONS_IDENTICAL_REVIEW_ONLY",
            "reason": "CHECKOUT_AND_DISPOSABLE_JAR_MATCH_NOT_PRODUCTION_APPROVAL",
            "source_migrations": len(local),
            "jar_migrations": len(packaged),
            "reviewed_future_versions": sorted(future),
            "identical_raw_bytes": True,
            "deployment_permitted": False,
            "candidate_jar_sha256": hashlib.sha256(jar.read_bytes()).hexdigest(),
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jar", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = validate(args.jar, args.source)
    except (OSError, ValueError, BadZipFile, RuntimeError, OverflowError):
        result = {
            "decision": "BLOCKED",
            "reason": "JAR_OR_SOURCE_UNREADABLE",
            "identical_raw_bytes": False,
            "deployment_permitted": False,
        }
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    # No success=0: candidate image lineage is evidence, not permission.
    return 4 if result["decision"].startswith("CANDIDATE_JAR_") else 2


if __name__ == "__main__":
    raise SystemExit(main())
