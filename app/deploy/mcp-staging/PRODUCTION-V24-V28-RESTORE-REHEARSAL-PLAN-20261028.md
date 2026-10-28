# G0-C production PRP MySQL V24 → V28 isolated restore/rehearsal — review plan

> **Source-only execution plan; technical gates remain NO-GO.**
> This record is not authority to snapshot or deploy the production PRP
> application, run Flyway, start a new database, copy personal records,
> access PRP tasks, or install the OAuth clients. G0/B2 approvals are
> not issued by GitHub code, CI or this document.

## What is actually established (operator evidence 2026-10-28)

| Dependency | Observed on real micor-server | Status |
| --- | --- | --- |
| Existing PRP production data target | `matrix-mysql` / schema `matrix_prp` | Known production target; no migration |
| Flyway V7 baseline / V8–V24 history | 1 V7 baseline + 17 applied SQL; **17/17 recorded signed CRCs match candidate** | `SOURCE_CRC_MATCH_REVIEW_ONLY`, not a release |
| Existing owner FK prerequisite | `prp_users(id)` signed BIGINT single-column PK, nonpartitioned InnoDB | Exact metadata preflight PASS |
| V25–V28 proposed names | 0 collisions with five proposed tables and five proposed FK constraints; no V25–V28 installed | `V25_V28_FK_DDL_SHAPE_MATCH_REVIEW_ONLY` |
| Historical and current *test Keycloak* backup isolated recoveries | 101 tables, 13 preexisting clients, reviewed two exact create/rollback, public JWKS parity | PASS only for test Keycloak; **not** PRP MySQL |
| Running V2 first-party artifacts | Both gateway and backend `oidc=ABSENT` | Cannot run actual ChatGPT owner linking |
| Real production MySQL consistent backup/restore | **Not performed / not attested** | Mandatory next independent gate |
| Authorized G0/B2 production release / public OAuth | **Not issued** | NO-GO |

## Owner/data target decision and precedence

The actual goal is to return **the owner's already-existing PRP tasks**
with the existing PRP account's authorization. A new isolated V2/18083
database would contain synthetic or newly created records and is **not**
proof of this objective. Preferred initial architecture to review is a
task-only, in-process MCP feature alongside the existing production
`TaskService` and scoped `MyBatisTaskRepository`; enable only
`prp.tasks.read` after authentic first-party owner linking.

This strategy changes the **production** Spring Boot application and
its schema: it is a separate, higher-impact change than the previously
recovered test Keycloak. Do not move old V2/legacy MySQL volumes or
merge divergent historical V24 files to obtain a superficial PASS.

## Production MySQL storage/capacity preflight prepared — not run on host

Before requesting any authorized MySQL production backup, use the
reviewed [read-only source-volume/capacity inventory](PRODUCTION-MYSQL-CLONE-CAPACITY-READONLY-20261028.md).
Its script `production_mysql_clone_capacity_readonly.py` checks exact
`matrix-mysql` container mount metadata, reports a redacted physical
data-directory footprint and source/backup filesystem headroom,
without database login, sensitive rows, data export, or state change.
The bounded size walk runs at `nice -n 15 ionice -c3` with a 30-second
timeout and requires an existing root-owned `0700` backup directory.

The initial heuristic is a same-filesystem free-space check of
3 × observed footprint + 4 GiB and 2 GiB available RAM. It is a
**planning approximation**, not sufficient proof that logical backup,
real isolated restore, production workload and write activity are
safe; separate filesystems or missing metadata require review.
Its `deployment_permitted=false` and `real_backup_performed=false`
never change. Offline synthetic host tests do not execute Docker
against the user server. No host operator result exists yet.

## Actual production MySQL capacity review and backup engine inventory (2026-10-28)

The operator ran `production_mysql_clone_capacity_readonly.py`
and received `CAPACITY_ESTIMATE_REVIEW_ONLY`, observing 3,570 MiB
physical MySQL data, 34,112 MiB free on the **same filesystem**
for both data and proposed backup, 3,518 MiB available RAM,
and a 14,806 MiB conservative capacity threshold. The target
service/MySQL were running and no backup was made. This is
**physical resource feasibility**, not independent recovery safety.

An additional fixed [backup consistency/engine/object inventory
SELECT](PRODUCTION-MYSQL-BACKUP-CONSISTENCY-READONLY-20261028.md)
is now available and has **passed actual disposable MySQL 8.4
positive/negative tests**. It reads production table-engine counts,
metadata-visible views/triggers/routines/events, binary logging and
GTID mode, without reading business data. Its purpose is to decide
whether simple transaction-consistent InnoDB logical export is
*plausible*, not to approve a backup or assert complete
information_schema visibility. The new query has **not been run on
production**. Do not take a snapshot until metadata scope, DBA access,
private backup destination and proper independent authorization
are reviewed.

## Mandatory private production copy workflow, not yet executed

**0. Authorize collection and resource scope.** The legitimate PRP
owner, DBA/recovery operator and change reviewer must agree on:
independent approval, exact target `matrix-mysql / matrix_prp`,
backup retention/encryption/storage, root/DB role permissions,
maintenance window/lock sensitivity, maximum CPU/RAM/disk use,
test-network isolation, delete/rollback owner, and emergency abort.
Observe existing workloads; do not rely on a default 20 GiB free-space
threshold without measuring **actual** DB/backup size. The snapshot
contains private task, finance, health, account and other application
records; no bytes or user records in GitHub/ChatGPT/CI.

**1. Select an internally consistent, comprehensive snapshot.**
For InnoDB a carefully controlled `mysqldump --single-transaction`
is a possible option; its consistency scope, current binary logging/
GTID mode, schema DDL changes during the dump, nontransactional
tables and routine/event/trigger coverage must be explicitly reviewed
by the DBA. Include table structures, rows, views, triggers, routines,
events, character sets and a reproducible Flyway metadata history
consistent with application writes. `--single-transaction` does not
alone protect from concurrent DDL or nontransactional storage engines.
If using a different physical/snapshot mechanism, document the
recovery point and restore requirements. Never export passwords to
shell arguments/logs or upload the dump off its approved private store.

**2. Verify integrity without assuming recovery.** Record a
protected timestamp/source ID, byte count, SHA-256 and safe
permissions; verify the archive/SQL is complete. **A hash or
`mysqldump` exit status is not a restore**. Never overwrite
a previous good backup.

**3. Restore into an isolated and non-public MySQL 8.4 clone.**
Use a completely new data volume, fixed explicit read-only source
file reference, separate credentials, no production DB mounts, no
public ports, bounded resources and deterministic cleanup. Restore
all required objects, preserve collations, constraints, PK/FK and
`flyway_schema_history`, then independently prove the original
V7 baseline + V8–V24 history and sensitive owner/task relations
using private, salted or HMAC digests/counters only. No real
identifiers, task descriptions, finance or health data in stdout or
GitHub CI artifacts. Do not run `flyway repair`,
`baselineOnMigrate`, `clean`, `DROP` or destructive reconciliation
against the source. Do not clone current app runtime secrets into
the disposable Spring app.

**4. Apply exactly reviewed V25–V28 only to that restored copy.**
Confirm immutable SQL source/JAR bytes and model compatibility first.
V25 creates `prp_mcp_write_drafts`, V26 `prp_mcp_client_grants`,
V27 `prp_mcp_identity_links` and `prp_mcp_link_tickets`,
V28 `prp_mcp_oidc_link_flows`; all have new FKs referencing
`prp_users(id)`. Compare source and post-migration Flyway
history/CRC, five added tables, FK/unique/index definitions,
exact counts, existing row hashes, sensitive owner/task relationships,
and behavior of the **actual prospective application artifact**
with MCP flags OFF. Run the existing PRP ordinary feature smoke
regressions, not just `prp_tasks_list`.

**5. Define rollback without data loss.** An additive DDL migration
may be irreversible under an already-used production application
without a separate authorized compensating plan; MySQL DDL and
Flyway bookkeeping cannot be assumed to roll back transactionally.
Do not restore a stale pre-cutover database over newer business rows.
Agree on a forward-fix/feature-disable path, app/JAR rollback
compatibility, handling of any post-snapshot writes and explicit
abort criteria (data count/digest, migrations, startup, owner
isolation or resource breach). Attest it in the independent review.

**6. Only a separately permitted test-to-live release** may follow
the completed production copy rehearsal, approved G0/B2 receipts,
final Nginx exact Host/SNI/raw URI route, reviewed Keycloak two-client
create-only registration, frontend identity-link artifacts and
real user consent. No production OAuth or public deployment from
the preceding review steps.

## Pass/fail rules

- **FAIL / NO-GO:** inconsistent snapshot, unknown source,
  unreviewed changes during dump, incomplete objects, mismatched
  Flyway CRC/DDL or owner-task digest, unexpected DDL, leaking
  personal data, cross-user scope escape, missing rollback/restore
  owner, or missing release approval.
- **Technical rehearsal PASS (review only):** independent restore
  on a protected clone, verified full original schema and
  owner/task record preservation, exactly four new migrations and
  five new MCP tables, functional build/migration smoke, isolated
  cleanup and recorded restore evidence.
- **Production release authorized:** only the original accountable
  human approval process, current backup/restore acceptance, exact
  route/client/app/DB change scope, data-continuity signoff and
  rollback owner can determine this. This document always remains
  `deployment_permitted=NO`.

**Do not repeat** the already-passed production Flyway 17/17 source
CRC, five-name FK metadata preflight, or test Keycloak recovery
without observed schema/source drift or a specific reviewer need.
