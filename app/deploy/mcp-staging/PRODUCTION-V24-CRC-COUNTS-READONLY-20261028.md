# Production V8–V24 checksum evidence — aggregated SELECT, no raw rows (2026-10-28)

> Operator-assisted verification only. No G0/B2, production migration,
> deployment, backup restore, SSH policy or OAuth activation is authorized.
> Do not post database passwords, source config, checksums, task rows or dumps
> to GitHub, CI artifacts or chat.

## Why this check is different

The owner observed the real `matrix-mysql` `matrix_prp` history:
exactly **one rank-1 V7 BASELINE** with NULL checksum, plus **17 SQL
migrations V8–V24**, all successful. This is a documented historical
lineage. The preceding read-only investigation verified the live Java
process connects to local port 3306 and the corresponding production
container. **The original V8–V24 checksum values have not yet been compared
against trusted candidate SQL**, and V1–V7 actual legacy DDL is not attested.

`production_v24_checksum_query.py` is a pure offline generator. It
imports the already CI-reviewed Flyway line-oriented CRC32 implementation
and computes reference values from an exact checked-out source revision.
It emits a **single read-only MySQL SELECT with a CTE of expected
V8–V24 scripts/checksums**. MySQL returns only:
- `schema_match`: `YES` only for `matrix_prp`.
- `history_rows`: must be exactly **18**.
- `baseline_rows_matched`: must be exactly **1**.
- `observed_sql_rows`: must be exactly **17**.
- `source_sql_rows_matched`: must be exactly **17**.
- `decision`: must be `SOURCE_CRC_MATCH_REVIEW_ONLY`, never a release approval.
- `deployment_permitted`: always `NO`.

Any unexpected historical row, rank, script, type, failed status,
NULL SQL checksum, changed source checksum or wrong database produces
`BLOCKED_OR_UNVERIFIED`. This query never SELECTs checksum values
or business records in its **output** and has no DDL/DML.

## Reproducible operator procedure (after independent access authorization)

The following are **preparation steps, not production deployment**.
On the production host the operator already has an isolated review
clone at `/root/matrix-prp-mcp-v2-staging`; do **not** change its
checked-out HEAD or the live application. Verify its origin and access
policy before use. Use an independently reviewed **pinned Git commit**
containing the script and original V1–V24 migration sources; do **not**
trust whatever branch tip happens to exist at execution time.

Example commands (the reviewer must pin the actual approved commit):

```bash
STAGING=/root/matrix-prp-mcp-v2-staging
BRANCH=test/mcp-authcode-privatejwt-refresh-20261024
PIN=<independently reviewed full 40-character commit>
git -C "$STAGING" fetch --no-tags origin "$BRANCH"
git -C "$STAGING" cat-file -e "$PIN^{commit}"
umask 077
REVIEW_DIR=$(mktemp -d /root/prp-v24-crc-review.XXXXXXXX)
git -C "$STAGING" archive "$PIN" \
  app/deploy/mcp-staging/production_v24_checksum_query.py \
  app/deploy/mcp-staging/review_production_flyway_history.py \
  app/backend/src/main/resources/db/migration \
  | tar -x -C "$REVIEW_DIR"
python3 -B "$REVIEW_DIR/app/deploy/mcp-staging/production_v24_checksum_query.py" \
  > "$REVIEW_DIR/aggregate-v24-readonly.sql"
```

The next command only invokes MySQL's existing **authorized**
`matrix_prp` account. It prompts interactively for the DB password
and never supplies a credential in the command line:

```bash
docker exec -it matrix-mysql mysql --protocol=socket \
  -u matrix_prp -p -D matrix_prp --table \
  -e "$(cat "$REVIEW_DIR/aggregate-v24-readonly.sql")"
```

A strictly approved existing SELECT-only account is preferable. If
the current account has more privileges, **do not infer that the
script is authorized to use those privileges**. Always review the
generated SQL locally before execution. Do not set `MYSQL_PWD`,
turn on `set -x`, post the source path, or export the raw database
checksum table. If any source pin, Git verification, authorization or
query parse fails, **STOP**; do not adjust production Flyway history,
grant extra rights or enable migrations.

This SQL returns only aggregate metadata; share only the resulting
coarse verdict, after reviewing that it contains no private material.
If `SOURCE_CRC_MATCH_REVIEW_ONLY` is returned, it proves only that
recorded SQL V8–V24 CRCs match the **candidate checkout**. It does
**not** prove the source matches the deployed JAR, or that manually
baselined V1–V7 schema is correct. Independently attested code
provenance, verified off-host backup + isolated restore, genuine
production DDL assessment, credential scope and G0/B2 remain required.

When finished, the private review directory contains **only candidate
source and SQL, not database exports**. A designated admin may remove
it after saving reviewed evidence under the approved change process.

## Evidence and testing

The generator is tested as part of the offline
`mcp-production-flyway-readonly-review.yml` contract and directly
against the genuine disposable MySQL V7-baseline → V24 → V28
integration flow in `mcp-legacy-v7-baseline-upgrade-review.yml`.
A disposable V24 should match; a disposable V28 must be blocked by
this intentionally V24-only preflight. Both are review-only.

This instruction does **not** demonstrate that an actual production
checksum comparison or off-host recovery has been carried out.
