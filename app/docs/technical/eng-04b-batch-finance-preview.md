# ENG-04B — Batched WeChat imported-identity preview lookups

## Goal

Before ENG-04B, `FinanceImportService.preview()` ran one
`SELECT COUNT(*) FROM prp_finance_source_links` per distinct nonblank
transaction ID, meaning up to **20,000 database round trips** for a
20,000-row import, in addition to the original staging INSERTs. This
stage replaces **preview-only read** N+1 with a bounded lookup.

## Changes

New `FinanceImportSourceLinkRepository` owns source-link lookup SQL.
The service preserves the existing row classification via
`FinanceImportPolicy.previewRowStatus`, ownership, file identity,
transactions and all INSERT/UPDATE SQL.

- Extract unique, nonblank submitted external transaction IDs in input
  order, splitting into chunks of at most **250**.
- Per chunk, execute one prepared SELECT of the *submitted* IDs that
  have matching `prp_finance_source_links` rows, constrained by
  `user_id=?` and `platform='WECHAT'`.
- Critically, use a derived submitted-ID relation and the **exact
  V21 `utf8mb4_unicode_ci` column collation**, so the returned IDs
  remain the original submitted strings even if matching stored IDs
  differ in case. Java lowercase/equalsIgnoreCase would not precisely
  reproduce MySQL collation.
- Never interpolate an external ID into SQL. The row-ID columns,
  tenant identity and all SQL values are bound parameters.
- One query for 1–250 IDs; 80 queries for 20,000 unique IDs; zero
  queries for an empty/blank-ID file. The original individual staging
  INSERTs are not batched yet and remain the next hotspot.

## Protecting ledger writes

A preview is advisory, **not the authoritative duplicate lock**.
`commit()` continues to use the original tenant-scoped
`SELECT ... FOR UPDATE` batch/row locks, check the source-link identity
**again for each mapped READY entry**, insert the ledger row and
globally unique external source link in the **same transaction**, and
update the import row as POSTED only after linkage. The V21 unique
index remains the final concurrent duplicate guard. No migration,
schema change, auto-posting or downgrade to weaker isolation.

## Tests

- `FinanceImportSourceLinkRepositoryTests`: 20,000 synthetic distinct
  rows -> 80 bounded lookups, 250 prepared external IDs plus tenant
  binding each, duplicate IDs de-duplicated, SQL-injection-looking
  text bound rather than concatenated, empty/blank files, and
  preservation of live commit-time duplicate lookup.
- `FinanceImportDatabaseIT`: real MySQL 8.4 with an existing
  external link; a second upload using uppercase variants of the
  source ID is still DUPLICATE; another user importing that same
  ID is READY; the original idempotent commit and cross-user
  batch access protections remain green.
- Existing CI: Spring Boot unit suite, finance and video database
  integration, migration checks, controller compatibility and
  Web/mobile builds.

## Limitations & next ENG-04 actions

The preview queries and **individual row INSERTs** are still part of
the same staging transaction, so for 20k rows there remain 20k inserts.
The optimization reduces **round trips for dedup reads**, not every
statement and does not promise measured runtime savings on production
data. To measure, run an isolated benchmark with non-sensitive
representative XLSX files, compare SQL query/roundtrip counts and
latencies, and then consider chunked staging INSERTs with identical
error rollback and original row order. Do not upload real bills to CI.

This is a Draft PR **stacked after ENG-04A PR #103**, independent of
ENG-03 production migration review. No production ALTER or controller
permission change. No merge into auto-publishing main until existing
release and data-integrity gates are satisfied.
