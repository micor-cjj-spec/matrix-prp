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
MAX_SQL_BYTES = 1024 * 1024
MAX_ZIP_ENTRIES = 50000
MAX_JAR_BYTES = 240 * 1024 * 1024


def validate(jar: Path, source: Path) -> dict:
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
    if set(versions) != EXPECTED_VERSIONS or len(versions) != len(EXPECTED_VERSIONS):
        return blocked("SOURCE_EXPECTED_V1_V29_INCOMPLETE")

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
