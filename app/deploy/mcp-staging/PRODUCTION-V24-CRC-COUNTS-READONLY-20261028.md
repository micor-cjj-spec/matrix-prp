# Production V8–V24 checksum evidence — aggregated SELECT, no raw rows (2026-10-28)

> Operator-assisted verification only. No G0/B2, production migration,
> deployment, backup restore, SSH policy or OAuth activation is authorized.
> Do not post database passwords, source config, checksums, task rows or dumps
> to GitHub, CI artifacts or chat.

## Production operator verified source CRC parity — 2026-10-28

**This result supersedes the earlier pending/unverified CRC wording below.**
The operator actually executed the pre-reviewed, SHA-pinned, fixed
`production_v24_crc_aggregate_readonly.sql` from
`44af5657d5712056e414c0290e78264e2de035e0` against the existing
production `matrix-mysql` database `matrix_prp`, using the
`matrix_prp` login with an interactive password prompt. The *first*
attempt failed **before SQL execution** because `docker exec -it`
was invoked from a non-TTY heredoc. The operator reran the query from
the interactive root shell; actual MySQL table output was:

```text
schema_match             YES
history_rows             18
baseline_rows_matched    1
observed_sql_rows        17
source_sql_rows_matched  17
decision                 SOURCE_CRC_MATCH_REVIEW_ONLY
deployment_permitted     NO
```

The successful query validates that all **17 applied V8–V24 Flyway
migration scripts, names, ranks and signed Flyway CRC values** match
the pinned candidate source, and that the rank-1 V7 baseline has
the expected shape. No production business/user/task data, raw
checksums, connection password or secret was shared; this query
only read `flyway_schema_history`. This materially reduces migration
lineage uncertainty; do not re-run the identical CRC test without drift.

**Not proven:** V1–V7 prebaseline DDL, current
`prp_users(id)` type/engine/PK needed by new foreign keys,
table/constraint name collisions for V25–V28, currently deployed
JAR/source equivalence, populated production restore with additive
migrations, or a data-loss-free rollback plan. The statement's
`deployment_permitted=NO` is intentional and remains correct.
**No production migration or G0/B2 authorization follows.**

**Next scoped compatibility check:** [V25–V28 owner-FK and new-table
DDL metadata preflight](PRODUCTION-V24-MCP-DDL-READONLY-PREFLIGHT-20261028.md)
uses a second fixed read-only aggregate SELECT on
`information_schema` and `flyway_schema_history`. It verifies
the actual `prp_users(id)` foreign-key target and proposed table/constraint
name collision conditions, without selecting actual user or task rows.
The query has passed both source-contract tests and real disposable
MySQL 8.4 positive/negative CI, but has not run against production.
A positive result remains `REVIEW_ONLY` and never approves migration.

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

## Preferred: single pinned, checked-in SQL (minimal operator commands)

The repository also contains
[`production_v24_crc_aggregate_readonly.sql`](production_v24_crc_aggregate_readonly.sql).
Offline CI asserts this static artifact equals **byte-for-byte** the
Python-generator output from the same reviewed V8–V24 source SQL.
The real isolated MySQL legacy V7→V24→V28 integration test executes
this same static artifact. This avoids any runtime Python or temporary
source checkout on the production host.

Once independent change-control review approves the SELECT-only metadata
query, an operator can fetch the branch in an **isolated existing review
clone only**, verify the **specific reviewed full SHA** and read the SQL
from that immutable Git object without checking out or installing files:

```bash
V2=/root/matrix-prp-mcp-v2-staging
PIN=<independently reviewed full 40-character commit>
git -C "$V2" fetch --no-tags origin test/mcp-authcode-privatejwt-refresh-20261024
git -C "$V2" cat-file -e "$PIN:app/deploy/mcp-staging/production_v24_crc_aggregate_readonly.sql"
```

After the `cat-file` check succeeds, inspect the SQL through the
approved review process and execute only using the existing, authorized
MySQL account with interactive password prompting:

```bash
docker exec -it matrix-mysql mysql --protocol=socket \
  -u matrix_prp -p -D matrix_prp --table \
  -e "$(git -C "$V2" show "$PIN:app/deploy/mcp-staging/production_v24_crc_aggregate_readonly.sql")"
```

**Do not run unpinned branch-tip SQL**, use the two-step git verification
above. The source CRCs are derived from the reviewed repository; neither
the Git object nor the SQL contains secret credentials. MySQL displays
only the aggregate verdict, not checksum values. A report of a source
CRC match is diagnostic and cannot confer release approval or replace
restored-copy schema checks.

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
