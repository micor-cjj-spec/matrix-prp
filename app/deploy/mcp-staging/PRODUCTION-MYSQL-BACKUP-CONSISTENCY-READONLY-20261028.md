# PRP production MySQL: backup consistency scope preflight (2026-10-28)

> **Review only.** No `mysqldump`, database writes, backups, restores,
> locks, service restarts, migration, Keycloak OAuth installation or
> G0/B2 approval performed by this document or SQL.
>
> Never upload database dumps, SQL rows, task/finance/health data,
> passwords, tokens, signing keys, or personal account material here.

## Capacity already observed on the real operator host

The SHA-pinned `production_mysql_clone_capacity_readonly.py`
was executed on `micor-server`. At inspection time: production
`matrix-mysql` and `matrix-prp.service` both running, physical data
directory footprint **3,570 MiB**, existing backup/data filesystem
free **34,112 MiB**, available memory **3,518 MiB**, same filesystem
for both, private backup parent confirmed. The conservative
capacity review requirement was **14,806 MiB** and the resource
estimator reported `CAPACITY_ESTIMATE_REVIEW_ONLY`; both
`real_backup_performed` and `restore_executed` were **false**.

This is sufficient to proceed to **backup planning**, not an assurance
that a full consistent logical snapshot and full isolated restore will
fit or have acceptable latency. Source database and proposed backup
directory share the same failure domain. A separately secured
backup location is needed for disaster-recovery protection.

Two other actual production read-only SQL checks already passed:
the V7 baseline plus **17/17 Flyway V8–V24 script CRC matches** and
the signed BIGINT `prp_users(id)` FK target / 5 MCP table and
5 foreign-key name collision check. Both still say
`deployment_permitted=NO`. No need to rerun these absent drift.

## Fixed SELECT-only consistency-scope probe

`production_mysql_backup_consistency_readonly.sql` queries
only `information_schema.TABLES`, `TRIGGERS`, `ROUTINES`,
`EVENTS`, the **count** of `flyway_schema_history` and
read-only server variables `@@GLOBAL.log_bin`, `@@GLOBAL.gtid_mode`.
It does **not** read actual `prp_users` or task rows, collect
identifiers, SQL text, row values, or backup bytes. It has one
fixed `matrix_prp` schema and a single SELECT statement.

It outputs only aggregate metadata:

| Field | Why it matters |
| --- | --- |
| `schema_match` | Reject unintended default DB/schema |
| `base_tables_visible`, `innodb_tables_visible` | Transactional table-engine inventory for possible consistent logical dump |
| `non_innodb_or_unknown_tables_visible` | Any non-InnoDB or unknown engine requires different consistency design |
| `views_visible`, `triggers_visible`, `routines_visible`, `events_visible` | Estimate object types whose inclusion/privileges must be verified |
| `server_binary_logging`, `server_gtid_mode` | Help DBA assess GTID/binlog restoration implications |
| `flyway_history_rows` | Ensure known production V24 history count has not drifted |
| `decision` | `VISIBLE_BASE_TABLE_ENGINES_INNODB_REVIEW_ONLY` or `BLOCKED_OR_UNVERIFIED` |
| `backup_approved`, `deployment_permitted` | Always `NO` |

**Critical visibility limitation:** `information_schema` can hide
objects based on current MySQL grants. A count of 0 triggers, routines
or events is NOT independent proof that none exist. Neither does
a correct engine count prove complete table privileges, lack of
concurrent DDL, transaction consistency, binary log/GTID recovery
readiness, data integrity or sufficient disk. A hypothetical
`mysqldump --single-transaction` requires a separate DBA review
of concurrency, objects, dump flags, role permissions, capture
window, secret handling and consistent recovery. A mixed-engine
result is an explicit STOP for that simplistic method.

## Operator usage (only after authorized metadata access)

The operator should use the original root shell with an interactive
TTY, a reviewed immutable source SHA, and the existing known
MySQL account without logging its password. No shell tracing,
dumping credentials, or unpinned SQL from the branch tip.

```bash
V2=/root/matrix-prp-mcp-v2-staging
BRANCH=test/mcp-authcode-privatejwt-refresh-20261024
PIN=REPLACE_WITH_REVIEWED_GIT_COMMIT
SQL=app/deploy/mcp-staging/production_mysql_backup_consistency_readonly.sql
git -C "$V2" fetch --no-tags origin "$BRANCH"
test "$(git -C "$V2" rev-parse FETCH_HEAD)" = "$PIN"
git -C "$V2" cat-file -e "$PIN:$SQL"
docker exec -it matrix-mysql mysql --protocol=socket \
  -u matrix_prp -p -D matrix_prp --table \
  -e "$(git -C "$V2" show "$PIN:$SQL")"
```

This is an **observation**, not change authorization. On error,
unknown privileges, non-InnoDB, unexpected version/DDL drift or
nontransparent object coverage, stop and reconcile through the
original authorized DBA review. Do not elevate MySQL privileges,
run `FLUSH TABLES WITH READ LOCK`, change binary log settings,
remove files, alter live tables, issue backups, enable Flyway,
or reconfigure Keycloak/PRP/Nginx to satisfy the probe.

## Source and disposable MySQL CI evidence (2026-10-28)

**Both current tests passed without any operator-server access:**

- [Offline metadata SQL safety #40716327676](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40716327676) — SUCCESS. The contract checks exactly one SELECT, fixed `matrix_prp`, metadata-only tables, no DML/DDL, fail-closed verdict and permanent NO permission.
- [Real disposable MySQL 8.4 #40716345146](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40716345146) — SUCCESS. An InnoDB-only synthetic schema returned `VISIBLE_BASE_TABLE_ENGINES_INNODB_REVIEW_ONLY`; adding one synthetic MyISAM table returned `BLOCKED_OR_UNVERIFIED`. CI logged `CI_MYSQL_BACKUP_ENGINE_METADATA_READONLY_POSITIVE_NEGATIVE=PASS` and `BUILD SUCCESS`. The disposable test does not establish the real production engine mix or completeness.

The fixed SQL source was introduced in Git commit
`1b71da2262bf6fd9a104d4689736a4ea2b9a1aa1`; its Git object remains unmodified by later documentation changes. **No user-host outcome for the new consistency probe exists yet.**

## Evidence boundary and next phase

Offline source-safety contract tests and **synthetic, disposable
MySQL 8.4 positive/negative** executions should be checked before
asking the operator to run this query; CI never contacts real PRP.
After a reviewed positive host observation, the next milestone is
approval of a **separate secure backup and fully isolated restore
target**, plus tests for unchanged owner/task counts and private
digests through V25–V28 and independent rollback. Only the
original G0/B2 authorization process can approve live changes;
this document always implies `deployment_permitted=NO`.
