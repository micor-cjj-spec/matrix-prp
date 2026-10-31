# PRP MCP — one Debian host, isolated MySQL restore plan (2026-10-29)

> **Design + synthetic CI only. No live PRP database dump or restore
> has been performed. Draft PR #113 remains Draft; original G0/B2
> approvals remain NO-GO.** Owner confirms they have **no spare server**.
> Do not purchase a second server just for a temporary dry run.

## Real disposable CI result: completed successfully (2026-10-29)

[One-host isolated MySQL backup → restore → additive MCP migration
workflow #40791821565](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40791821565)
**SUCCESS** at commit
`efa7e8e70abfa1e5b4e7e08ff93f541951319c3b`.
The actual runner used two isolated **synthetic** MySQL 8.4 Docker
containers and new volumes, with no host-published port. Its
`mysqldump` included trigger, routine, event and view; restoring the
archive into the other container preserved all four object types
(`CI_SYNTHETIC_MYSQL_BACKUP_RESTORE_ALL_OBJECT_CLASSES=PASS`).
After recovery, V25–V28 created exactly five new MCP tables and five
MCP owner FKs **only on the clone**, while source owner/task
fingerprints stayed the same
(`CI_SYNTHETIC_ONE_HOST_ISOLATED_RESTORE_AND_V25_V28=PASS`).
The run explicitly confirmed
`NO_PRODUCTION_DB_OR_USER_DATA_ACCESSED=YES`,
`PRODUCTION_BACKUP_PERMITTED=NO` and
`G0_B2_RELEASE_PERMITTED=NO`.

**Evidence boundary:** This fixture has a minimal synthetic original
schema and synthetic records; it does **not** prove recovery of the
real 57-table production schema, full Flyway history or private data.
The existing separate genuine Flyway V7-baselined V24→V28 CI covers
that migration pathway with synthetic records, but neither CI
constitutes a real PRP production database backup.

## Supplemental synthetic archive tamper detection (2026-10-29)

The CI fixture now additionally hashes the temporary synthetic SQL
archive, verifies it before restore and deliberately modifies a
separate synthetic copy to confirm the digest would no longer match.
It deletes the tampered copy and the disposable SQL source file
during cleanup. This detects a simple byte-change in that controlled
test; a SHA-256 digest alone does **not** authenticate the writer,
prevent malicious replacement of both the file and digest, or
guarantee a coherent **real** MySQL transaction snapshot. For
actual data, keep a separately authenticated, encrypted off-host
copy and require a complete isolated restore.

## Full V7-baselined V24 dump→restore→V28 verification — PASS

[Real disposable MySQL 8.4 complete V24 source/clone review
#40793268099](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40793268099)
**SUCCESS** at source commit
`266be74a1eefcc5cc8b187c01f701641a1d4e7b9`.
The workflow ran the authentic reviewed Flyway V1–V7 schema,
modelled the observed production V7 historical baseline,
migrated the synthetic source through V8–V24, seeded synthetic
per-owner tasks (24 and 3), finance, video and vocal records,
and took a full logical MySQL dump. It restored the dump to
a **separately named MySQL 8.4 container/volume** and compared
synthetic business-row fingerprints and the original V7-baselined
18-record history, then applied **exactly Flyway V25–V28 to the
clone only**. All five required MCP objects appeared only in
the clone; the source remained V24 and all original synthetic
user/task/finance/video/vocal fingerprints stayed unchanged.

Actual green CI job log includes
`CI_SYNTHETIC_TRUE_V7_BASELINE_V24_SOURCE_SEEDED=YES`,
`CI_FULL_V24_SQL_ARCHIVE_TAMPER_REJECTED=YES`,
`CI_FULL_SYNTHETIC_V24_RESTORED_CLONE_V28_OWNER_TASK_FINANCE_VIDEO_VOCAL_PRESERVED=YES`,
`CI_SOURCE_DB_STAYED_V24=YES`,
`CI_FULL_V7_BASELINE_V24_DUMP_RESTORE_V28_CLONE=PASS`,
and `CI_NO_PRODUCTION_DATA_OR_HOST_ACCESS=YES`.

An initial [CI #40793142474](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40793142474)
failed at host-side JDBC connectivity because a completely
`--internal` Docker network prevented the runner from reaching
loopback-published container ports. The revised **CI-only**
unique Docker bridge uses `127.0.0.1:13308/13309` explicitly;
rerun passed. This change does **not** justify public DB ports in
the production host rehearsal.

**Boundaries:** Even a full authentic *source-built* V24 schema
may differ from the user's actual historically pre-V7 manually
baselined tables, application/data drift, privileged objects,
and deployment artifact. Synthetic fingerprints are not private
user-data digests. This is a stronger technical regression,
**not** a restored production backup or G0/B2 release signoff.
No real user/finance/health/task data was copied to GitHub/CI.

## Exact production-observed V24 table-count parity: 57 (2026-10-29)

The source-built full V7-baselined V24 test has been tightened to
require **exactly 57 BASE TABLE objects**, matching the owner's
separately collected production `matrix_prp` visible-base-table
count of 57. It no longer accepts an arbitrary count above 50.
The updated Java CI, including original source V24, copied V24
and post-V28 clone checks, was re-run:
[full schema backup/restore #40793594246](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40793594246)
**SUCCESS** at source SHA
`5505aa2a5c80145f4794fcb5bbf9b2a9a95e251c`.
Original data fingerprints, V7-baselined 18 migration records,
SHA integrity and exact four new migrations still passed.
The clone has **five additive MCP tables** beyond these original
57 and preserves the source's owner/task/finance/video/vocal data.

This confirms the two independently measured *table counts*
agree, but **does not prove table DDL, constraints, grants, rows,
pre-V7 historical data or routines match production**. Only
independently authorized private restoration of the actual
production MySQL backup can test those.

## Stronger full V24 schema backup/restore CI (2026-10-29)

A second, more representative **synthetic-only** workflow now
exists:
[`mcp-full-v24-backup-restore-review.yml`](../../../.github/workflows/mcp-full-v24-backup-restore-review.yml)
with test class
`IsolatedV24BackupRestoreMcpV28IT.java`. It differs from the
previous minimal synthetic table fixture:

1. Constructs the genuine repository **V1–V7** MySQL schema in a
   disposable source container, models the observed **V7 baseline**,
   and applies the genuine original **V8–V24** Flyway SQL.
2. Seeds synthetic, per-owner **tasks, finance transactions, video
   assets, and vocal songs**; preserves full original Flyway history.
3. Runs real `mysqldump` on that synthetic V24, confirms a
   private SHA digest and rejects a modified synthetic copy, then
   restores to another new volume/container.
4. Compares original **source vs restored-clone** business-row and
   V7-baselined Flyway history fingerprints; applies Flyway V25–V28
   only on the restored clone and confirms exactly five additions,
   while the source stays V24.

For CI, the host-side Java JDBC test needs loopback access at
`127.0.0.1:13308` and `127.0.0.1:13309`. The disposable containers
therefore use a unique CI-only Docker bridge, with **both published
ports explicitly bound to loopback**. This is not the same as an
`--internal` network with no published ports, which is still the
preferred **production-host restore design** when no host-side JDBC
test needs to reach the clone. The first CI attempt at
[run #40793142474](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/40793142474)
showed host JDBC was blocked when both were combined; the network
topology has been corrected for the next attempt. These source-only
changes do not touch the owner's production host, and the full
57-table private-data restore remains **not performed**.

## Decision: separate failure domains, not necessarily separate servers

A recovery **rehearsal** can run on the **same** Debian host as
production, using a new Docker MySQL container/volume attached to an
internal-only network and no published port. This technically isolates
the new database *logically*, but **does not protect against failure of
that physical host, its underlying disk or compromise of its root
account**. Do not claim a same-host file is an independent recovery
backup.

To protect the real PRP before any actual production app upgrade,
independently store an encrypted second copy **outside the Debian
server**. Options requiring **no second server**: provider-managed
disk/cloud snapshot with a separately controlled recovery lifecycle;
encrypted object storage (OSS or similar); or an encrypted copy
downloaded to a personal computer, iPhone file storage or removable
drive and verified there. Do not upload plaintext SQL to GitHub,
ChatGPT, CI, a public web link, or an unaudited file-sharing account.
The archive encryption key/recovery credential should be retained
independently of the server and not pasted into chat, shell history,
process arguments or logs. If off-host protection is not yet
available, the same-host exercise can prove a **technical migration
rehearsal**, but **must not** be accepted as disaster-recovery
readiness or justification for upgrading production.

## Grounded operator source: already complete, do not repeat

| Checked on actual operator host | Value |
| --- | --- |
| Production application and MySQL | `matrix-prp.service` / `matrix-mysql` both running |
| Production data/schema | `matrix_prp`, V7 Flyway baseline + 17 V8–V24 SQL migrations |
| V8–V24 original source CRC | 17/17 matched |
| Real owner ID and proposed MCP FK names | signed BIGINT single-column InnoDB PK, zero five-table/FK collisions |
| MySQL source data directory | 3,570 MiB; **physical**, not expected dump size |
| Free disk / available RAM at review | 34,112 MiB / 3,518 MiB |
| Backup parent | root-private; data and backup on the **same filesystem** |
| Visible base tables | 57/57 InnoDB, zero visible non-InnoDB |
| Object types visible | 0 views/triggers/routines/events **under current account only** |
| Binary log and GTID | binlog ON, GTID OFF |
| Production MySQL backup / restore | Not performed |
| Running V2 OAuth client-link application | frontend and backend OIDC markers both ABSENT |
| G0/B2 authorization | NO-GO |

The 33.31 GiB free disk and 3.44 GiB available RAM suggest a
**carefully bounded** same-host rehearsal may be possible, but a
physical data directory, logical dump, temporary encrypted file,
separate MySQL data volume and concurrent disk writes have different
sizes. The optional new container must have conservative memory/CPU
limits, use distinct new Docker names, no host ports, non-production
volumes and I/O backpressure. No capacity test can promise service
latency or safe free-space thresholds for an actual run.

## Proposed phases and strict boundaries

**A — available now: synthetic pipeline verification in GitHub.**
The workflow
[`.github/workflows/mcp-single-host-mysql-recovery-fixture.yml`](../../../.github/workflows/mcp-single-host-mysql-recovery-fixture.yml)
creates two *temporary*, synthetic MySQL 8.4 Docker volumes and two
containers attached to a job-owned internal network. It seeds synthetic
owners/tasks and placeholder Flyway metadata, plus a view, trigger,
routine and event. It executes a real
`mysqldump --single-transaction --quick --hex-blob --routines
--events --triggers --set-gtid-purged=OFF --no-tablespaces`
on the disposable source, restores into the empty clone, checks
synthetic task fingerprint and object counts, and applies the **real
candidate V25–V28 SQL only to the clone**. It checks that five MCP
tables/FKs exist only in the clone and that the synthetic source is
unaltered. The workflow owns its own containers/volumes and cleans up.
It has **no access to the owner's host, MySQL or PRP data**. Its
minimal pre-MCP fixture is intentionally *not* a full production
schema; the existing real Flyway V7→V24→V28 CI separately covers
full migration lineage on synthetic data.

**B — before any real backup: original owner/operator authorization.**
Approve a limited scope for:
- capture of the full real `matrix_prp` schema and row data with
  correctly scoped DB credentials and no secrets exposed in shell
  arguments, Docker environment dumps or logs;
- verification of the snapshot account's true privileges, visibility
  of views/triggers/routines/events and prohibition on concurrent DDL;
- design of a consistent InnoDB snapshot; binlog ON, GTID OFF
  recovery time and backup flags; error handling if dump or
  encryption stream fails; encrypted output and retention;
- a separate failure-domain storage copy and an independently
  controlled decryption key, before production upgrade is authorized;
- resource caps, current on-host free disk and memory, emergency
  abort/restart owner and cleanup behavior; no unknown Docker volumes
  or previously edited V2 Compose files touched.

A plan or GitHub CI success is **not** a release receipt; no code or
assistant should invent the original G0/B2 signoff.

**C — approved production dump, only after B.** Use a securely
managed encryption recipient/key and stream the logical dump without
persistent **plaintext** staging files. Verify process exit status
(`pipefail`), encrypted archive integrity, storage space, copy
verification and recovery-key availability; preserve timestamps and
binlog recovery assumptions. Don't declare success from only a hash.
Do not run `mysqldump`, `mysql -pPASSWORD`, Docker image pull,
backup network transfer or a production mysql login in a pipeline
unless the owner explicitly approves the exact capture scope.

**D — authorized same-host restore.** Allocate a brand-new, dedicated
MySQL Docker volume, no production DB/shared mount, internal-only
network and **no host-published port**. Use a *separate* database
identity/password, prevent outbound jobs/webhooks, and cap RAM/CPU.
Only the verified encrypted archive should be decrypted directly
into this clone; never output plaintext SQL or personal data into
logs, GitHub/ChatGPT or world-readable temporary files. Keep the
original production service and schema untouched. Prevent teardown
of any existing workload if a partially failed clone has name/volume
collisions: stop and require human review, do not prune globally.

**E — rehearsal and verification.** Confirm full original Flyway
V7 baseline + V8–V24 signed CRC values and complete object coverage
in the restored copy, then privately verify owner/task/finance and
other data counts and *non-reversible keyed* fingerprints without
printing rows, salts or keys. After those checks, apply **only**
immutable V25–V28 with the candidate Flyway runner to **the restored
copy**. Validate exactly five new MCP tables, five FK definitions,
no original row digest drift, application startup with MCP disabled,
and no cross-owner task exposure. Define rollback preserving every
post-snapshot write. No `flyway repair`, `clean`, history rewrites,
`baselineOnMigrate` or app production cutover from this rehearsal.

**F — release separately.** Real `prp_tasks_list` requires
actual user-task continuity, reviewed app artifact, correctly linked
Keycloak owner identities, consent, only `prp.tasks.read`, exact
Nginx Host/TLS/raw URI routes, first-party browser OIDC code **present
in the installed app**, original signed release approvals and tested
rollback. A same-host restored clone alone does not satisfy this.

## Technical decision criteria

- Synthetic CI PASS proves the **logical dump→isolated restore→new
  tables** plumbing works on **synthetic** data only.
- A real restored private clone with exact original owner/task
  preservation is a **technical rehearsal**, not an independent
  off-host disaster recovery backup.
- No actual production backup has been exported; no user data has
  been placed in GitHub, ChatGPT or a third-party service by this work.
- Until a protected off-host copy and independent signoff exist,
  `backup_approved=NO`, `g0_b2_approval=NO`,
  `deployment_permitted=NO`.


## Addendum 2026-10-31 — distinct **V2 V28→V29** recovery candidate (not production V24)

This is a **separate staging database and change target** from the
production V7-baselined \`matrix_prp\` V24→V28 pathway above.
Do not apply production V24 backup procedures, V25–V28 migration steps,
schema names or accounts to the live \`prp-mcp-v2-mysql-1\`.

**Grounded operator evidence (read-only):** the active isolated V2
MySQL 8.4 has a continuous V1–V28 Flyway history, 28/28 CRCs matching
Draft PR #131, no failed migration, a real V28 temporary-grant lease
table, and **no** V29 history row or OIDC flow table. V29 DDL preflight
found InnoDB \`prp_users\` with signed BIGINT non-null one-column
primary key, no target table or foreign-key-name collision. The
running V2 backend and gateway images still lack OIDC Controller/Service
and callback/start/finish JavaScript markers.

**Implemented synthetic-only rehearsal:**
\`.github/workflows/mcp-v28-backup-restore-v29-review.yml\` runs
\`IsolatedV28BackupRestoreMcpV29IT.java\` in a disposable GitHub runner
against *two synthetic, separately named MySQL 8.4 Docker containers and
volumes*. It:
1. Builds the canonical full V1–V28 schema and inserts two synthetic
   owners with tasks, finance, client grants, identity link, temporary
   grant lease and one-use ticket;
2. Creates a full synthetic \`mysqldump\`, checks its SHA-256 and a
   deliberately corrupted copy, then restores only into an initially
   empty clone;
3. Compares eight selected existing-table row fingerprints, Flyway
   V1–V28 history, and pre-migration table count across source and
   restored clone;
4. Runs **only V29 on clone**, proves one new OIDC table and its
   owner FK, denies orphan flow records, checks that all selected
   historical row fingerprints remain unchanged and that source stays
   at V28; destroys its own ephemeral resources.

[First green synthetic V28 dump→restore→V29 CI #41197658567](https://github.com/micor-cjj-spec/matrix-prp/actions/runs/41197658567)
passed both phases. Synthetic checks do **not** certify that every
unpopulated source table has identical data or establish actual V2 backup
validity, recoverability, service compatibility or production owner
linking. These private, synthetic backup bytes were never published.

**Real V2 next gate, not performed:** independently authorized
complete snapshot of the *actual isolated V2 database*, verified
recovery into a newly named separately protected database without
touching its original containers/volumes, original V28 history and
user/ACL data reconciliation, and V29 on restored copy only. Confirm
a rollback that can preserve writes made after the backup. Off-host
protection and genuine G0/B2 release authorization remain separate
requirements. Do **not** execute the synthetic workflow against the
V2 host or change its hard-coded CI host/URL guards to point to the
existing database. No current V2, production DB, external OAuth client
or public route was modified by this work.
