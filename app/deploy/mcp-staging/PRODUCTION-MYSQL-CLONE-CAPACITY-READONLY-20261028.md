# Production PRP MySQL clone backup capacity — host metadata only (2026-10-28)

> **Not a backup, authorization, Flyway migration or release.** G0/B2
> remain NO-GO. The full PRP production owner/task database has
> **not** been exported or restored; Keycloak's successful restoration
> was a separate *test Keycloak PostgreSQL* database.

## Source-only safe preflight

`production_mysql_clone_capacity_readonly.py` inspects only the
existing production service `matrix-prp.service` and the exact
existing `matrix-mysql` Docker container. It does NOT log into MySQL,
read task/user/finance/health rows, access Docker environment fields,
export SQL, copy files, create directories, start containers, restart
services, write to an active database, or change Nginx/Keycloak.

- Uses Docker **read-only inspect** for `State.Status`,
  `Config.Image` and `Mounts` (not `Config.Env`).
- Requires exactly one existing mounted MySQL data path at
  `/var/lib/mysql`, a known `mysql:8.x` image, a real
  non-symlink absolute host volume/bind source and a root-private,
  existing backup parent `/root/prp-mcp-backups` (does not create
  this parent or grant permissions).
- Estimates DB file footprint using **filesystem directory metadata**
  only: `nice -n 15 ionice -c3 du -sk -x -- <verified-mount>`,
  with **30-second timeout**. This can cause bounded background
  metadata I/O on the host; authorize/review its operational impact
  if the database is under heavy write load. It never prints the
  actual mount path, user database table names or file contents.
- Reads `/proc/meminfo`, free bytes on both data and proposed
  backup filesystems and whether they share a device. Does not
  invoke `docker exec`, `mysqldump`, `mysql` or `pg_dump`.

It emits a redacted JSON envelope with `data_footprint_mib`,
`backup_fs_available_mib`, `data_fs_available_mib`,
`mem_available_mib`, container state, ownership of existing
private backup directory and an **estimate**. It reports
`CAPACITY_ESTIMATE_REVIEW_ONLY` only if the same filesystem has
at least 3 × measured data footprint + 4 GiB free and at least
2 GiB memory available; this is a heuristic, **not an appropriate
backup storage allocation or a release permit**. A different
filesystem returns `SEPARATE_FILESYSTEM_REVIEW_REQUIRED`.
If unavailable/missing/unsafe inputs or low memory are found,
it returns `BLOCKED_OR_UNVERIFIED`; if insufficient free space,
`INSUFFICIENT_FOR_CONSERVATIVE_SAME_FS_REVIEW`.

No result asserts that a consistent `mysqldump` will fit,
compression ratio, binary log/event/trigger coverage, detached
restore capacity, spare IO, write-lock impact, encryption, backup
retention, or rollback. In particular, the **source data volume size
is not equal to logical SQL backup size**. A real recovery budget
must be independently reviewed based on DB structure and active
load, including backup location, isolated clone/temporary volume,
full recovery and post-backup writes.

Every result explicitly includes
`real_backup_performed=false`, `restore_executed=false`,
`database_modified=false`, `services_restarted=false`,
`g0_b2_approval_issued=false` and
`deployment_permitted=false`.

## Operator reading (only from exact reviewed SHA)

This command runs in a non-interactive shell because it has **no
password prompt or docker -it**. The Git worktree is never reset and
the V2 Compose local edits are preserved:

```bash
set -Eeuo pipefail
V2=/root/matrix-prp-mcp-v2-staging
BRANCH=test/mcp-authcode-privatejwt-refresh-20261024
PIN=REPLACE_WITH_REVIEWED_COMMIT
FILE=app/deploy/mcp-staging/production_mysql_clone_capacity_readonly.py
git -C "$V2" fetch --no-tags origin "$BRANCH"
test "$(git -C "$V2" rev-parse FETCH_HEAD)" = "$PIN"
git -C "$V2" cat-file -e "$PIN:$FILE"
git -C "$V2" show "$PIN:$FILE" | python3 -B -
```

The source has offline synthetic tests with a fake Docker/host,
including image/container/mount drift, symlinks and unknown
paths, low memory/disk, separate filesystem and forbidden write
commands. No CI workflow or test accesses the operator's real
Docker daemon or MySQL.

## Decision after collecting this information

1. If `CAPACITY_ESTIMATE_REVIEW_ONLY`, **review** the business data
   backup strategy, active MySQL table engines/DDL/GTID/binlog modes,
   complete scope (data, views, triggers, routines, events),
   encryption, external backup storage, resource headroom,
   retention/cleanup and expected restore point. Do not call this
   operational approval.
2. If blocked, **do not create new host directories, install a
   database image, remove files, prune volumes or reconfigure
   production** solely to satisfy this script. Inspect status
   safely and choose a different authorized backup/clone host.
3. Only after the original independent authorization, take a
   complete consistent production MySQL backup without leaking
   sensitive rows; restore on a separate isolated environment,
   attest owner/task preservation and apply V25–V28 **only to
   the clone**. This is specified in
   [PRODUCTION-V24-V28-RESTORE-REHEARSAL-PLAN-20261028.md](PRODUCTION-V24-V28-RESTORE-REHEARSAL-PLAN-20261028.md).

Existing PRP production application, test Keycloak, V2 Nginx and
both databases stay unchanged by this preflight.
