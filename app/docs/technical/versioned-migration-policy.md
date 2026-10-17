# Versioned empty-table migration contracts

Ordinary new empty tables no longer require a controller edit or an increase of
`reviewed_through_version`. From V22 onward, submit the Flyway SQL, the matching
rule in `app/deploy/migration-policy.json`, and application/tests in one reviewed
PR. Keep existing migration files and existing rules immutable.

Example rule (replace the digest with SHA256 of committed UTF-8/LF SQL bytes):

```json
{
  "schema_version": 1,
  "rules": [
    {
      "version": 22,
      "file": "V22__feature_notes.sql",
      "sha256": "<64 lowercase hex characters>",
      "mode": "create-empty",
      "tables": ["prp_feature_notes"]
    }
  ]
}
```

Supported migrations contain only explicit CREATE TABLE statements for canonical
lowercase `prp_*` names, with primary keys and InnoDB/utf8mb4. The table list must
match SQL order exactly. Ordinary columns, indexes and foreign keys are supported;
expression defaults, CHECK/generated columns, cross-schema references, temporary
tables, CREATE-AS/LIKE, advanced table options, executable/block comments and SQL
escapes require specialist review. Statements must end with semicolons. Java migrations, callbacks, repeatables and nested migration resources are also rejected. Every
post-V21 migration must have exactly one rule; unlisted SQL or tables fail closed.
Limits are intentionally bounded (128 rules, 64 tables per migration, 1 MiB SQL,
256 KiB contract). Unsupported schemas/modes never fall back to permissive rules.

CI forbids a pending controller candidate from publication without an explicit
hold, preventing candidate-only green CI from being treated as live readiness.
CI checks source/contract consistency and exercises the exact reviewed controller.
Packaging puts a contract in the archive with the exact release commit, includes
its digest in release metadata, and compares it with actual migration bytes in
the built JAR. Production independently repeats the JAR/contract/commit checks
before migration. A changed policy, changed SQL, wrong commit, duplicate version,
missing rule or missing policy for future versions is rejected.

Checksums are consistency bindings, not signatures or proof of human approval.
The trust boundary remains the existing authorized restricted SSH publisher,
protected-main workflow provenance, environment controls and reviewed PR. No new
signing/SSH keys, root SSH privileges, shell, SFTP or sudo permissions are granted.
CI and the single root-owned controller contain byte-identical validator code;
changing that validator is a controller change, not an ordinary policy update.

Before upgrading a live database the controller restores a complete backup into
a unique isolated database, applies the target migrations and verifies every
historical primary-key/full-row fingerprint and normalized old table definition.
Only declared pending-version tables may be added, all initially empty. Existing
rows/ownership, V19 backfill, private-video and unknown-table guards remain. The
same rules and DDL evidence are applied at final production cutover. Missing DDL
evidence fails closed. Reaching V23 does not re-authorize V22's tables as new.

Backfills, old table changes, data transformations, triggers or new policy modes
need a separate reviewed preservation design. Never label those changes
`create-empty` or add an allow-any mode to get a green build. The existing V19
independent expected-content/ownership check remains a special approved case.

## Controller upgrade and publication hold

`admin_upgrade_contract_controller.py` is administrator-only. It validates exact
old/new digests, restricts existing function changes, backs up original controller,
configuration and SQL, and rehearses both the unchanged V21 artifact and a
synthetic V22 artifact adding an otherwise unlisted table on restored isolated
data. The synthetic artifact is never published and V22 is not added to the real
repository/database. Forged commit/table contracts are tested independently.
Only after unchanged live V20 data/service are proved is the controller replaced
atomically. Root review/backup/receipt paths are `/root/prp-contract-review`.
Rollback restores exact controller bytes only; it never restores live SQL. Every
replacement, including rollback, requires independent SSH inventory measurement.

The one-time `app/deploy/publication-hold.json` file prevents automatic and manual
mutating publication while this controller capability is installed/attested.
Its presence is restrictive; malformed holds fail closed. Read-only check and
the existing main-only SSH acceptance remain available. No production environment
branch policy is relaxed. Main can therefore contain the real installed hashes
and be verified without silently publishing the pending V21 application.

When application publication is explicitly requested, remove the hold file in a
reviewed PR. Existing successful-main-CI -> build -> safety gates -> backup and
isolated rehearsal -> publish -> health checks then resume normally. Do not
disable a guard, run a hidden deploy, or interpret a held/skipped publish as an
application release. Credentials remain in GitHub Secrets.
