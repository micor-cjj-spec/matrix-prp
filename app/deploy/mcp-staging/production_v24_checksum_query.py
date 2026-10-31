#!/usr/bin/env python3
"""Generate a fixed SELECT-only aggregate comparison for production V7->V24.

No database driver, credentials, production data, network or mutations.
The expected CRC reference is derived ONLY from the reviewed checkout's
original V8..V24 Flyway SQL. A MATCH is REVIEW_ONLY, never deployment approval.

Run the generated SQL only through an independently authorized existing
SELECT-only MySQL session targeting the verified PRP production schema.
"""
import argparse
import os
import re

from review_production_flyway_history import source_crc32, source_scripts

SCHEMA = "matrix_prp"
BASELINE = "<< Flyway Baseline >>"
FIRST_SQL = 8
LAST_SQL = 24
EXPECTED_SQL_ROWS = LAST_SQL - FIRST_SQL + 1
EXPECTED_ROWS = EXPECTED_SQL_ROWS + 1


def sql_literal(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.]+", value):
        raise ValueError("UNSAFE_SOURCE_SQL_FILENAME")
    return "'" + value + "'"


def build_query(expected_schema=SCHEMA):
    if expected_schema not in (SCHEMA, "matrix_prp_upgrade_ci"):
        raise ValueError("UNSUPPORTED_SCHEMA")
    scripts = source_scripts()
    crc = source_crc32()
    if set(scripts) != set(range(1, 30)) or set(crc) != set(scripts):
        raise ValueError("CANDIDATE_SOURCE_INCOMPLETE")
    selects = []
    for version in range(FIRST_SQL, LAST_SQL + 1):
        number = crc[version]
        if type(number) is not int or not -(2**31) <= number < 2**31:
            raise ValueError("INVALID_SOURCE_CRC")
        selects.append(
            "SELECT " + sql_literal(str(version)) + " AS version, "
            + sql_literal(scripts[version]) + " AS script, "
            + str(number) + " AS checksum, " + str(version - 6)
            + " AS installed_rank"
        )
    reference = "\nUNION ALL\n".join(selects)
    # No raw checksum, source filename, account, JDBC URL or business data
    # is returned. The only output is aggregate metadata and a fail-closed
    # verdict. A versioned SQL row must match rank, script, checksum and success.
    sql = f"""WITH expected AS (
{reference}
)
SELECT
  IF(DATABASE() = '{expected_schema}', 'YES', 'NO') AS schema_match,
  COUNT(*) AS history_rows,
  SUM(CASE
    WHEN h.installed_rank=1 AND h.version='7' AND h.type='BASELINE'
      AND h.script='{BASELINE}' AND h.checksum IS NULL AND h.success=1
    THEN 1 ELSE 0 END) AS baseline_rows_matched,
  SUM(CASE WHEN h.type='SQL' THEN 1 ELSE 0 END) AS observed_sql_rows,
  SUM(CASE
    WHEN h.type='SQL' AND e.version IS NOT NULL
      AND h.installed_rank=e.installed_rank
      AND h.script=e.script AND h.checksum=e.checksum AND h.success=1
    THEN 1 ELSE 0 END) AS source_sql_rows_matched,
  CASE WHEN DATABASE()='{expected_schema}'
     AND COUNT(*)={EXPECTED_ROWS}
     AND SUM(CASE
       WHEN h.installed_rank=1 AND h.version='7' AND h.type='BASELINE'
         AND h.script='{BASELINE}' AND h.checksum IS NULL AND h.success=1
       THEN 1 ELSE 0 END)=1
     AND SUM(CASE WHEN h.type='SQL' THEN 1 ELSE 0 END)={EXPECTED_SQL_ROWS}
     AND SUM(CASE
       WHEN h.type='SQL' AND e.version IS NOT NULL
         AND h.installed_rank=e.installed_rank
         AND h.script=e.script AND h.checksum=e.checksum AND h.success=1
       THEN 1 ELSE 0 END)={EXPECTED_SQL_ROWS}
    THEN 'SOURCE_CRC_MATCH_REVIEW_ONLY'
    ELSE 'BLOCKED_OR_UNVERIFIED' END AS decision,
  'NO' AS deployment_permitted
FROM flyway_schema_history AS h
LEFT JOIN expected AS e ON h.version=e.version;"""
    return sql


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ci-disposable-schema", action="store_true",
                        help="Only from the dedicated GitHub disposable MySQL workflow")
    args = parser.parse_args()
    schema = SCHEMA
    if args.ci_disposable_schema:
        expected_url = (
            "jdbc:mysql://127.0.0.1:13308/matrix_prp_upgrade_ci"
            "?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=Asia/Shanghai"
        )
        if not (
            os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("RUNNER_OS") == "Linux"
            and os.environ.get("PRP_CI_DISPOSABLE_LEGACY_BASELINE_ONLY") == "YES"
            and os.environ.get("MATRIX_PRP_DB_URL") == expected_url
        ):
            parser.error("CI_DISPOSABLE_SCHEMA_NOT_AUTHORIZED")
        schema = "matrix_prp_upgrade_ci"
    print(build_query(schema))


if __name__ == "__main__":
    main()
