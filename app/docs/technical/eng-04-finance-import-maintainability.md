# ENG-04A — Finance import business-rule extraction

## Scope

Behavior-preserving refactor of the WeChat XLSX bill import pipeline.
FinanceImportService retains transaction orchestration; the new package-private
FinanceImportPolicy owns five business invariants for independent unit testing:

- Select and validate source account keys (including blank and 128-character limit)
- Sanitize the original filename while preserving its 255-character suffix bound
- Classify duplicates without redundant database lookups for repeated IDs
- Validate mapped payment accounts as live, CNY and tenant-owned
- Construct expense ledger records with exact owner, account, amount, status,
  original merchant/note, transaction date and timestamps

## Explicit non-changes

- 5 MiB XLSX maximum, original parsing and file SHA256 idempotency unchanged
- Risky refunds/transfers stay REVIEW; same-file/existing source links become
  DUPLICATE; only approved READY items can enter the ledger
- Missing payment-account mapping still leaves rows pending; do not guess
- Tenant-scoped batch/row FOR UPDATE locks, source-link unique index, ledger
  insert and POSTED transition stay inside the original database transaction
- No API contract, existing SQL, database structure, Flyway migration, release
  controller or SSH policy changes
- No new automatic posting and no new external integrations

## Verification

New FinanceImportPolicyTests cover blank/long source, filename path stripping,
duplicate lookup short-circuit, review preservation, foreign/deleted/non-CNY
account refusal and exact expense-row field mapping.

Existing FinanceImportDatabaseIT verifies real MySQL READY/REVIEW counts,
idempotent upload/commit and cross-tenant access refusal. Existing CI retains
controller integrity, schema migrations, MySQL finance tests and Web/mobile.

## ENG-04 next steps

- Move import SQL into a tenant-scoped repository with a separate review of
  transaction/locking semantics
- Measure and separately optimize preview N+1 source-link existence checks
  under representative 20,000-row files with concurrent duplicate protection
- Introduce typed row states and an audit state-machine after compatibility
  fixtures exist for previously imported data

This is a separate Draft PR based on main. Do not merge merely because it
passes tests: merging to main may trigger production auto-publish.
