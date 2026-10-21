"""ENG-03A: offline review preflight for a very narrow additive-column DDL subset.

This module does NOT authorize a production Flyway migration. The independently
installed, root-owned publisher still supports only approved create-empty contracts.
No SQL is executed, no server is contacted, and no migration policy is modified.
"""
import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

MAX_CANDIDATE_BYTES = 8192
_IDENTIFIER = r"prp_[a-z][a-z0-9_]{0,58}"
_COLUMN = r"[a-z][a-z0-9_]{0,58}"
_TYPE = r"(?:BIGINT|INT|DATE|DATETIME\(6\)|DECIMAL\([0-9]{1,2},[0-9]{1,2}\)|VARCHAR\([0-9]{1,4}\))"
_CANDIDATE = re.compile(
    rf"ALTER TABLE (?P<table>{_IDENTIFIER}) "
    rf"ADD COLUMN (?P<column>{_COLUMN}) (?P<column_type>{_TYPE}) NULL, "
    r"ALGORITHM=INSTANT;"
)


@dataclass(frozen=True)
class NullableColumnCandidate:
    table: str
    column: str
    column_type: str
    sql_sha256: str

    def review_report(self) -> dict:
        return {
            "schema_version": 1,
            "classification": "SPECIALIST_REVIEW_REQUIRED",
            "production_authorized": False,
            "controller_upgrade_required": True,
            "operation": "ADD_NULLABLE_COLUMN",
            "table": self.table,
            "column": self.column,
            "type": self.column_type,
            "algorithm": "INSTANT",
            "lock": "IMPLICIT_DEFAULT",
            "sql_sha256": self.sql_sha256,
        }


def parse_candidate(raw: bytes) -> NullableColumnCandidate:
    """Accept one exact statement; reject comments, data writes and all other DDL.

    Lexical eligibility is not proof that an ALTER is supported by the real table
    layout, current server version, metadata locks or active traffic.
    """
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_CANDIDATE_BYTES:
        raise ValueError("Candidate SQL must be 1..8192 bytes")
    if any(c < 32 and c not in (9, 10, 13) or c > 126 for c in raw):
        raise ValueError("Only printable ASCII SQL with ordinary whitespace is accepted")
    sql = " ".join(raw.decode("ascii").split())
    match = _CANDIDATE.fullmatch(sql)
    if match is None:
        raise ValueError("Only one bounded nullable ADD COLUMN with INSTANT is reviewable")
    column_type = match.group("column_type")
    if column_type.startswith("VARCHAR"):
        length = int(column_type[8:-1])
        if not 1 <= length <= 1024:
            raise ValueError("VARCHAR length must be 1..1024")
    if column_type.startswith("DECIMAL"):
        precision, scale = (int(n) for n in column_type[8:-1].split(","))
        if not 1 <= precision <= 38 or not 0 <= scale <= precision:
            raise ValueError("Invalid DECIMAL precision or scale")
    return NullableColumnCandidate(
        table=match.group("table"),
        column=match.group("column"),
        column_type=column_type,
        sql_sha256=hashlib.sha256(raw).hexdigest(),
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Offline, non-authorizing migration candidate review")
    parser.add_argument("--sql", required=True, type=Path, help="Local candidate SQL file; never executed")
    arguments = parser.parse_args(argv)
    try:
        candidate = parse_candidate(arguments.sql.read_bytes())
    except (OSError, ValueError) as error:
        parser.exit(2, f"Candidate rejected: {error}\n")
    print(json.dumps(candidate.review_report(), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
