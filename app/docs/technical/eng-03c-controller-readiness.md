# ENG-03C — Production controller migration-readiness review

**Status: proposal and CI-only rehearsal; production authorization DENIED.**

This document is a design review for a *future* change to the root-owned
`/usr/local/sbin/prp-release` controller. It does not modify that controller,
`app/deploy/approved/prp-release.py`, `controller-manifest.json`,
`migration_policy.py`, or `migration-policy.json`. There is no Flyway V24.
Only the independently installed `create-empty` mode is allowed today.
The ENG-03A and ENG-03B Draft PRs (#96 and #97) must be reviewed first.

## New synthetic proof in CI

In two **fixed, disposable** MySQL 8.4 schemas on the GitHub-hosted runner:

1. Create a table with two synthetic owner-scoped rows.
2. Use `mysqldump --single-transaction` to capture that table, restore it
   into the **second isolated schema**, and compare complete old-row projections
   and table-definition fingerprints before changing anything.
3. Apply the exact `ALGORITHM=INSTANT` nullable ADD COLUMN **only** on the
   restored copy; demonstrate that the source schema and data did not change.
4. Run old-style SQL `INSERT (old_columns...)` and old-style `SELECT`
   against the expanded copy; run new-style SQL including the new nullable
   column; confirm old records remain readable, and users/IDs remain intact.
   **These are SQL-compatibility probes, not actual old/new application
   binary or API compatibility tests.**
5. Hold a transaction that has read the restored table, attempting a second
   synthetic instant ALTER with `SET SESSION lock_wait_timeout=1`. It must
   fail with a metadata-lock wait timeout, not fall back to `INPLACE` or
   `COPY`, and leave rows/DDL unmodified. After releasing the transaction,
   the same exact instant ALTER should complete.

The source database is itself a synthetic test fixture, **not a copy of a
production backup**. The test runs only with fixed `127.0.0.1`, user
`matrix_prp`, disposable schema names, and CI test credentials; no host,
database name, SSH key, or real data is accepted as input.

MySQL explicitly says INSTANT DDL can briefly acquire an exclusive metadata
lock, and `lock_wait_timeout` controls metadata-lock acquisition attempts.
The value applies per lock attempt; it does **not** provide a hard guarantee
of the entire migration's wall-clock duration. See:

- https://dev.mysql.com/doc/refman/8.4/en/alter-table.html
- https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html
- https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl-operations.html

## Production approval prerequisites — all currently pending

| Gate | Required independent evidence | Present in ENG-03C? |
| --- | --- | --- |
| P1. Real backup | Recent complete and checksummed production DB + media backup; encrypted storage, restore receipt, original protected | **No** |
| P2. Restored rehearsal | Restored *actual* representative DB in a separate, least-privilege schema; before/after full old-row and ownership fingerprints | **No** |
| P3. MySQL preconditions | Exact production 8.4 patch, InnoDB row format, FULLTEXT/index constraints, table size and INSTANT limits validated | **No** |
| P4. DDL timeout + locks | Actual migration/Flyway session has bounded metadata-lock wait; active transaction contention and timeout verified | **No** |
| P5. Old/new application | Prior deployed JAR/Web and candidate JAR/Web both pass authenticated read/write smoke tests on expanded rehearsal DB with private-data isolation | **No** |
| P6. SQL provenance | Exact reviewed new Flyway SQL, source commit, artifact/JAR digest and frozen V24-or-later version (no collisions) | **No** |
| P7. Controller preservation | Independent review of minimal **actual installed** controller patch, old/new SHA256, changes to existing-DDL guards, forbidden SQL and rollback tests | **No** |
| P8. Controller administration | Root-only backup, permission-preserving atomic install, administrator approval, service unchanged, SSH/SFTP/forwarding policy independently re-attested | **No** |
| P9. Publication readiness | Approved manifest, signed-off hold release, protected-main CI, production environment gates and independent post-cutover row/schema/health receipt | **No** |

A green CI means **only** the synthetic feasibility tests passed.
It **never** upgrades P1–P9 to complete or generates a production pass token.

## Future controller design requirements — not implemented

A separate administrator-reviewed controller patch must:

- Bind exact `V24+` SQL bytes, hash, filename, source commit, release artifact,
  existing table and expected **pre-DDL** definition to a reviewed new mode,
  without changing the existing `create-empty` rules.
- Restore full production backup into a newly allocated isolated schema
  and perform the *same* Flyway migration there, measuring DDL execution
  and old-row/ownership/index/constraint/trigger preservation.
- Compare the pre-DDL snapshot to the on-host production version and table
  definitions immediately before stop/cutover; refuse unexpected schema
  drift, duplicate columns, concurrent deployments or missing evidence.
- Bound **the actual Flyway DDL connection's** `lock_wait_timeout`;
  setting it in a *different* mysql client session is ineffective.
  Stop on timeout. Never silently substitute `ALGORITHM=INPLACE/COPY`.
- Reject negative/destructive DDL, unsafe defaults/backfills, noncanonical
  identifiers, unknown table options, data modifications, or a `create-empty`
  rule falsely authorizing an old-table change. Preserve the
  version-specific V19 backfill and all existing privacy gates.
- Keep a controlled application-only rollback path *only after* old binaries
  prove compatibility with the expanded schema. MySQL DDL is not undone
  transactionally. Do not automatically drop a new column or replace current
  user data with a stale snapshot.
- Require administrator installation and a new independent controller/SSH
  inventory attestation before a publication hold is lifted. No root shell,
  additional SSH/SFTP rights, token/secret extraction, or hidden deployment.

## Explicit hold conditions

Any missing independent evidence in P1–P9, a failing synthetic/real rehearsal,
an unverifiable MySQL version or expected DDL, a metadata-lock timeout, a
misleading reviewer contract, a controller SHA mismatch, changed historical
fingerprints, incomplete authenticated old/new JAR tests, or partial backup
restoration means **STOP — DO NOT PUBLISH**.

The exact installed root controller is *not* the legacy repository
`server-release.py`. Do not replace it with that file or with any proposed
helper. Preserve the current independent deployment boundary.
