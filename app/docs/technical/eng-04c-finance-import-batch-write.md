# ENG-04C — transactional batched import staging

ENG-04B reduced preview source-link lookups from up to 20,000 queries to
80 bounded queries (250 distinct IDs per query), but still issued one
individual JDBC INSERT call per imported row.

ENG-04C adds a **separate FinanceImportStagingRepository**:
- Classify all parsed rows in original sheet order with the unchanged
  FinanceImportPolicy and ENG-04B duplicate-identity prefetch.
- Persist staging rows in JDBC `batchUpdate` chunks of up to **250**
  records, passing all 15 column values as prepared-statement parameters.
  Keep `NOW(6)`, the original per-row metadata, and the V21 schema.
- Reject missing/short JDBC update-count arrays, `EXECUTE_FAILED`,
  zero counts and unexpected row counts. Accept one affected row or
  `Statement.SUCCESS_NO_INFO` (driver-dependent success).
- Execute **all chunks inside the existing `@Transactional preview()`**
  call, including the initial batch-header INSERT. Any failed chunk throws
  and must roll back the header and all previously inserted chunks.
- Keep **commit() unchanged**: live per-row source-link duplicate checks,
  tenant-scoped `FOR UPDATE` locks, atomic ledger/source-link insertion and
  MySQL unique-index idempotency remain the final authority.

## Evidence

Unit tests simulate 20,000 rows -> **80 JDBC batch calls**. They check
parameter order, owner ID, transaction date/amount, status binding, a
partial final chunk, invalid update counts and exceptions. This is a
JDBC method-call count, **not a guaranteed 99.6% network-trip reduction**:
whether a MySQL driver rewrites batched INSERTs depends on connection
configuration, and 20,000 actual row inserts are still required.

Integration tests on disposable MySQL 8.4 create a **510-row synthetic
WeChat XLSX** and verify original sourceLine order, READY/REVIEW/
DUPLICATE classification, repeat-upload idempotency and tenant isolation.
A second MySQL integration test injects a duplicate `source_line` in
the second chunk and checks that both the batch header and all first
250 staged rows are **rolled back**.

## Non-changes and residual risk

No real bills used, no existing row migrations or SQL DDL, no new
auto-posting, no controller/SSH permissions and no API changes.
This is a stacked Draft PR after ENG-04A/#103 and ENG-04B/#104, with a
production publication hold.

The JDBC driver's packet composition and production latency have **not**
been benchmarked. Further tuning requires isolated measurements with
synthetic representative XLSX distributions, plus duplicate-concurrency
tests against MySQL's original source-link unique index. No release
approval can be inferred from a synthetic CI pass.
