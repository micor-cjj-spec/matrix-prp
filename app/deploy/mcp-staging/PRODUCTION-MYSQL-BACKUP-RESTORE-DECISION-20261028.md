# Production PRP MySQL: backup/restore decision after real metadata preflights (2026-10-28)

> **Decision packet only; no production backup or deployment authorization.**
> The owner's PRP database includes confidential and potentially sensitive
> account, task, financial and health data. No database export belongs
> in a repository, ChatGPT, CI logs, or an unapproved remote service.
> Draft PR #113 remains unmerged. G0/B2 are NO-GO.

## Closed: current operator-read-only discovery

- Actual `matrix-mysql` / `matrix_prp`: one V7 Flyway baseline
  plus V8–V24 (18 rows total); all 17 recorded V8–V24 signed CRCs
  match the pinned candidate source. No V25–V28 applied.
- Actual `prp_users(id)` on InnoDB: signed BIGINT, single primary
  key, nonpartitioned. Five new MCP table names and five FK names
  have **zero** observed collisions.
- Actual MySQL data directory: **3,570 MiB**, same filesystem
  as candidate private backup directory; that filesystem had
  **34,112 MiB** free and **3,518 MiB** RAM available
  at measurement. Physical size and resource headroom are **not**
  a logical backup/restore capacity guarantee.
- Actual metadata scoped to `matrix_prp`: **57 visible base
  tables, all 57 InnoDB**; 0 visible non-InnoDB/unknown-engine
  tables; 0 visible views, triggers, stored routines and scheduled
  events, with **visibility conditional on the MySQL account's
  privileges**. MySQL binary log ON; GTID mode OFF; 18 migration
  history rows. A first interactive login yielded error 1045;
  the retry succeeded with the exact pinned SELECT.
- Real **test Keycloak PostgreSQL** current snapshot isolated
  restoration passed 101 tables, preserved 13 clients and exercised
  exact two-client create+rollback; this does NOT restore PRP MySQL.
- Actual V2 gateway and backend both report `oidc=ABSENT`;
  registering clients alone will not implement first-party linking.

**Stop the repeated metadata-testing loop here** unless real schema,
source, login role, services or backup prerequisites change.
The missing evidence is not another SELECT but an independently
protected **production data snapshot + actual isolated recovery**.

## Required decisions before any sensitive export

| Decision / check | Required disposition / responsible party |
| --- | --- |
| Legitimate approval to export production data | Explicit owner/DBA change scope, where the dump may be stored, who can access it and when it is destroyed |
| Source correctness | Fixed `matrix-mysql` container and `matrix_prp` schema; verify current image/version, owner, app/runtime build before the window |
| Authorized noninteractive backup identity | Verify exact MySQL grants **without disclosing passwords**; no temporary privilege escalation, no database root shortcut, no secrets in shell history/argv, GitHub/ChatGPT logs or process lists |
| Complete object inventory | With an appropriately privileged reviewer, confirm 57 observed tables aren't merely privilege-filtered; distinguish genuine absence of views/triggers/routines/events from 0-visible counts |
| Transaction-consistent strategy | Document MySQL 8.x method, `--single-transaction` snapshot behavior, `--quick`, trigger/routine/event inclusion, views, concurrent-**DDL ban**, non-InnoDB tables and error detection |
| Binary log and GTID | Binary log ON, GTID OFF observed. Define snapshot reference time, binlog coordination, recovery-point objective and what happens to writes after the snapshot; choose explicit GTID-related dump/import behavior |
| Backup location/security | Prefer independently encrypted, access-controlled, off-host storage outside the currently shared failure domain. Never treat same-filesystem backup alone as disaster recovery |
| Availability/resource ceiling | Observe active application write load, query and I/O duration, disk/RAM budget and operator abort criteria; stop rather than impair production |
| Restore host isolation | Independent MySQL service/container, fresh data volume, no production volume mount, no public DB listener, separate credentials and network; prevent duplicate external jobs/webhooks |
| Preservation tests | On PRIVATE clone only compare 57-table visibility, original Flyway V7 baseline+17 CRCs, data totals and confidential per-owner/task digests *without printing private rows* |
| V25–V28 rehearsal | Only after clone proves baseline, apply immutable reviewed four migrations on the clone, validate exactly five additive MCP tables and five FKs and unchanged original data |
| Rollback/retention | Define data-safe rollback, handling changes since backup, disable-feature/app rollback paths, time-bound backup destruction/retention and independent signoff |

## Why the immediate next change is NOT production Flyway or OAuth

A matching source CRC and an InnoDB-only visible table set are
**necessary but insufficient** for in-place upgrade. During a
logical backup, `--single-transaction` can give a consistent
InnoDB data view only within its supported concurrency assumptions;
DDL activity can invalidate that view. It does not independently
establish correct object privileges, binary log recovery point,
routines/events, encrypted storage, successful restore or
cross-table real-user task preservation. MySQL DDL generally cannot
be treated as atomically rolled back alongside application data.

Because the goal is **the owner's existing PRP tasks**, the preferred
architecture to review remains a task-read-only MCP resource
*inside* the existing production PRP application. A synthetic
isolated V2/NewDB upgrade cannot substitute for the true owner
data. Once the production clone is proven and an independent
G0-C production change/rollback decision is authorized, an
approved app build and exact `prp.tasks.read` tool allowlist can be
tested with MCP off, then owner-bound OAuth. Separately review G0/B2
Keycloak clients, first-party callbacks and Nginx exact public
routes. No extra scopes, writes or unreviewed cross-db access.

## Completion criteria

**Technical restore rehearsal complete** requires a protected,
complete and consistent current production MySQL snapshot, successful
restore in an isolated data store, identity/row-count/digest
preservation and unchanged original business behavior, correct
V25–V28-only additive migration and owner-bound task regression.
It must be independently attested by the responsible operator.

**Release permitted** requires the actual controller's approval and
rollback evidence, not success labels from shell scripts, GitHub CI
or this plan. It is currently **NO**. No production export,
MySQL migration, Nginx reload, Keycloak client registration or
real ChatGPT `prp_tasks_list` has been executed by this planning work.
