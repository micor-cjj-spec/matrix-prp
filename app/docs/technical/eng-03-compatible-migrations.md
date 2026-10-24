# ENG-03A · Compatibility expansion rehearsal (review only)

This stage creates **no production migration capability**. The installed root-owned
publisher and `app/deploy/migration_policy.py` still approve **only** the
`create-empty` mode (see [versioned migration policy](versioned-migration-policy.md)).
Do not label an ALTER migration `create-empty`, change pinned controller digests,
or raise an approval ceiling. The production historical-table-definition guard
deliberately rejects changes to existing tables.

## Narrow candidate preflight

A reviewer may check one **proposed**, untracked SQL statement:

```sql
ALTER TABLE prp_finance_transactions
  ADD COLUMN source_platform VARCHAR(32) NULL,
  ALGORITHM=INSTANT;
```

```sh
python3 app/deploy/expand_candidate.py --sql /path/to/proposed-candidate.sql
```

The report carries the raw SQL SHA256, table, column and type, plus explicit
`production_authorized: false` and `controller_upgrade_required: true`.
This is **not** a release artifact or a signature. The CLI does not execute SQL.

The classifier recognizes a single explicit `ALTER TABLE prp_* ADD COLUMN`
statement, a small bounded type allowlist, `NULL`, and `ALGORITHM=INSTANT`.
Explicit `LOCK` modifiers are rejected. It rejects multiple statements, changes/removals, updates,
non-null columns, defaults, indexes, identifiers outside the canonical subset,
comments, cross-schema references, executable SQL comments and exotic DDL.
It does not permit existing SQL migration files or the production controller to
be modified, and cannot bypass GitHub branch protection.

## CI rehearsal

The `db-migration-integration` job initializes a disposable database
`matrix_prp_expand_verify` on its **CI-only MySQL 8.4 service** and applies a
fixed synthetic candidate to a two-row table. It verifies original data and
owner IDs are unchanged, the new field is nullable and historical rows have
NULL in that column, and a second SQL replay is rejected. The integration test
refuses other hostnames, database names, credentials and non-CI execution.

A passing dry-run only proves the narrow example works on that MySQL 8.4
environment. Real production tables can have different metadata, indexes,
size, MySQL versions, traffic and metadata-lock behavior. MySQL 8.4 rejects
explicit `LOCK=NONE` with `ALGORITHM=INSTANT`; even instant changes may
briefly need metadata locks and cannot promise a zero-wait migration. There is **no** authorization to run this ALTER
on existing PRP tables.

## Required follow-on review before enabling production ALTER

1. Obtain an independently reviewed controller change and exact installed
   controller attestation; keep a publication hold until approved, and do not
   change the SSH/permissions boundary.
2. Bind a future contract to the exact migration SQL, source commit and JAR,
   including the affected *existing* table and expected column definition.
3. Restore real backups into isolated MySQL, rehearse the same ALTER against
   representative table sizes, confirm preservation of every old column and
   row/ownership fingerprint, and validate indexes, constraints and lock impact.
4. Adopt expand → backfill → contract, with separate approval for backfill
   batches and destructive drops. Keep the application backward compatible
   while earlier code could be rolled back.
5. Validate production preconditions (server version, precise old DDL, active
   release/schema), require human authorization, fail closed for unreviewed
   changes, and record verified post-cutover evidence.

**Rollback:** Revert only application binaries while both versions tolerate
the expanded schema. Never execute a destructive automatic database rollback
or restore backups over actively written data.

ENG-03A intentionally remains a Draft until its existing and new CI tests pass;
it must not be merged in the mistaken belief that ALTER deployment is enabled.
