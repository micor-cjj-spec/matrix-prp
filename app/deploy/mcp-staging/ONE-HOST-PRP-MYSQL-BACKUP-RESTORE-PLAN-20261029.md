# PRP MCP — one Debian host, isolated MySQL restore plan (2026-10-29)

> **Design + synthetic CI only. No live PRP database dump or restore
> has been performed. Draft PR #113 remains Draft; original G0/B2
> approvals remain NO-GO.** Owner confirms they have **no spare server**.
> Do not purchase a second server just for a temporary dry run.

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
