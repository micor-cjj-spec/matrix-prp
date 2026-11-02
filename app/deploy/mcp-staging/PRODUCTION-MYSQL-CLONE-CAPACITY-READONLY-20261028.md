# Production PRP MySQL clone backup capacity — host metadata only (2026-10-28)

> **Not a backup, authorization, Flyway migration or release.** G0/B2
> remain NO-GO. The full PRP production owner/task database has
> **not** been exported or restored; Keycloak's successful restoration
> was a separate *test Keycloak PostgreSQL* database.

## Actual operator resource check — PASS as an estimate (2026-10-28)

The owner ran `production_mysql_clone_capacity_readonly.py` from
the immutable Draft commit `dd1928543252382c6f836c83c7223dd9e4c09d79`.
It completed with the external sentinel `READ_ONLY_COMPLETE`.
The exact bounded non-secret results included:

| Operator-observed attribute | Result |
| --- | --- |
| `mysql_running` | `true` |
| `prp_service_active` | `true` |
| `mysql_image_allowlisted` / `data_mount_reviewed` | both `true` |
| `data_footprint_mib` | `3570` |
| `backup_fs_available_mib` | `34112` |
| `data_fs_available_mib` | `34112` |
| `same_backup_and_data_filesystem` | `true` |
| `mem_available_mib` | `3518` |
| `backup_parent_root_private` | `true` |
| `conservative_same_fs_review_requirement_mib` | `14806` |
| `capacity_envelope` | `CAPACITY_ESTIMATE_REVIEW_ONLY` |
| `real_backup_performed` / `restore_executed` | both `false` |
| `database_modified` / `services_restarted` | both `false` |
| `g0_b2_approval_issued` / `deployment_permitted` | both `false` |

The 34,112 MiB observed free space exceeds the initial 14,806 MiB
review heuristic by 19,306 MiB, but this is a **physical data volume
footprint**, not an actual logical backup size or the space needed
by an independently isolated restored copy under concurrent writes.
Available RAM 3,518 MiB is a point-in-time observation, not a
promise of safe concurrent backup/clone load. Backup and data root
are on the **same filesystem**, so this location alone must not
count as an independent off-host disaster-recovery copy.

This closes only the **initial resource envelope inventory**.
No new backup was made and no full PRP MySQL recovery has been tested.
An authorized operator still needs actual workload/engine/GTID/
routines/trigger coverage, a private backup destination with independent
failure domain, encryption/retention rules, and a reversible migration
rehearsal on a separately isolated clone. **Do not repeat the exact
capacity test absent resource drift or an operational reviewer need.**

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
